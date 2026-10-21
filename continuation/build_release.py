"""Capture immutable checkpoint boundaries and build independently verifiable release volumes.

This reads the research workspace. It never submits, stops or modifies jobs.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import datetime as dt
import json
import math
from pathlib import Path
import shutil
from continuation.artifacts import pack_volume
from continuation.layout import BATCHES,REPO,sha,write_json

def source_path(source,original):
    path=Path(original)
    if str(path).startswith('/mnt/workspace/ReCogDrive/'):
        return source/str(path).split('/ReCogDrive/',1)[1]
    if path.is_file():return path
    for old,new in [('/mnt/yehr_workspace','/mnt/data_and_weight/WM_Group/yehr_workspace'),
                    ('/mnt/data/','/mnt/data_and_weight/')]:
        if str(path).startswith(old):
            candidate=Path(str(path).replace(old,new,1))
            if candidate.is_file():return candidate
    raise FileNotFoundError(path)

def entry(path,target,expected=None):
    path=Path(path).resolve()
    return dict(source_path=str(path).lstrip('/'),path=str(target),bytes=path.stat().st_size,
                sha256=expected or sha(path))

def create_plan(source,out):
    source=Path(source).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    plan_path=out/'PLAN.json'
    if plan_path.exists():return json.loads(plan_path.read_text())
    b1,b2,b3,b4=[source/n for n in BATCHES]
    profiles={name:[] for name in ['resume','repair42','teacher_train','teacher_validation',
        'metrics_development','metrics_evaluation','reference','expansion']}
    bulk=json.loads((REPO/'research_snapshot/BULK_ASSETS.json').read_text())
    for item in bulk['assets']:
        profiles[item['profile']].append(entry(source/item['workspace_path'],item['workspace_path'],item['sha256']))
    capture=dict(schema=1,captured_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),groups={},
        source_hardware='16 PPU-ZW810E devices per H/T/HT group',
        target_hardware='8 NVIDIA A800 devices; numerical and RNG backend migration is explicit',
        native_snapshot_unmodified=True,source_index_sha256=sha(REPO/'research_snapshot/INDEX.json'))
    for group in ['H','T','HT']:
        run=b4/'runs'/('distillation_main_v4_'+group)
        latest=json.loads((run/'LATEST_CHECKPOINT.json').read_text())
        if sha(b4/latest['path'])!=latest['sha256']:raise ValueError('Checkpoint not immutable')
        config=b4/'configs/distillation_main_v4'/(group+'.json')
        best=json.loads((run/'BEST_DEVELOPMENT.json').read_text())
        checkpoints={b4/latest['path'],b4/best['checkpoint']['path']}
        checkpoints.update((run/'checkpoints').glob('*_epoch0[123]_micro000000.pt'))
        capture['groups'][group]=dict(latest=latest,best_development=best,
            original_config=str(config.relative_to(source)),original_config_sha256=sha(config),
            checkpoint_files=[str(x.relative_to(source)) for x in sorted(checkpoints)])
        for path in sorted(checkpoints):profiles['resume'].append(entry(path,path.relative_to(source)))
        for name in ['BEST_DEVELOPMENT.json','ranks/rank00/PREFLIGHT.json']:
            original=run/name;frozen=out/'captured'/group/Path(name).name
            frozen.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,frozen)
            profiles['resume'].append(entry(frozen,original.relative_to(source)))
    for rel in ['provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V2.json',
                'runs/full_context_replay_v1/AGENT_ACCEPTANCE.json',
                'analysis/full_context_replay_v1/SUMMARY.json']:
        profiles['resume'].append(entry(b4/rel,(b4/rel).relative_to(source)))
    write_json(out/'captured/PORTABLE_SNAPSHOT.json',capture)
    profiles['resume'].append(entry(out/'captured/PORTABLE_SNAPSHOT.json','PORTABLE_SNAPSHOT.json'))
    scenes=json.loads((b4/'manifests/R2_TRAINING_SCENES_V2.json').read_text())
    train=set(json.loads((b4/'manifests/TRAIN_INDICES_V2.json').read_text()))
    development=set(json.loads((b4/'manifests/DEVELOPMENT_512_V1.json').read_text()))
    targets=json.loads((b4/'analysis/full_context_replay_v1/CASE_INDEX.json').read_text())
    def target_items(item):
        relative=Path(item['path']);folder=b4/relative.parent
        profile='teacher_train' if item['global_index'] in train|development else 'teacher_validation'
        return profile,[entry(folder/'RESULT.json',Path(BATCHES[3])/relative,item['record_sha256']),
            entry(folder/'full_context.npz',Path(BATCHES[3])/relative.parent/'full_context.npz',item['arrays_sha256'])]
    with ThreadPoolExecutor(max_workers=12) as pool:
        for number,(profile,items) in enumerate(pool.map(target_items,targets),1):
            profiles[profile].extend(items)
            if number%10000==0:print(json.dumps(dict(phase='target_inventory',cases=number,total=len(targets))),flush=True)
    # Metric caches are needed for epoch-end development; model training itself does not score trajectories.
    # Original cache bytes enable reproduction without rebuilding caches with a different serializer.
    test=json.loads((b2/'manifests/frozen_evaluation_test_rows_v1.json').read_text())
    for cohort,rows in [('navtrain',scenes),('navtest',test)]:
        def metric_item(pair):
            index,row=pair
            path=source_path(source,row['metric_cache'])
            profile='metrics_development' if cohort=='navtrain' and index in development else 'metrics_evaluation'
            return profile,entry(path,Path('_data/metrics')/cohort/row['log_name']/'unknown'/row['token']/'metric_cache.pkl')
        with ThreadPoolExecutor(max_workers=12) as pool:
            for number,(profile,item) in enumerate(pool.map(metric_item,enumerate(rows)),1):
                profiles[profile].append(item)
                if number%10000==0:print(json.dumps(dict(phase='metric_inventory',cohort=cohort,cases=number,total=len(rows))),flush=True)
    # Only Base and fixed R2 references are needed by student evaluation, not the entire 42-way tensor.
    import numpy as np
    for cohort in ['navtrain','navtest']:
        folder=b3/'analysis'/('first42_'+cohort+'_v1')
        selected=np.load(folder/'selected.npy',mmap_mode='r')[:,5]
        ids=np.arange(len(selected));q=np.load(folder/'scores.npy',mmap_mode='r');t=np.load(folder/'trajectories.npy',mmap_mode='r')
        path=out/'captured'/f'{cohort}_references.npz'
        np.savez_compressed(path,Base_quality=np.asarray(q[:,0]),R2_quality=np.asarray(q[ids,selected]),
            Base_trajectories=np.asarray(t[:,0]),R2_trajectories=np.asarray(t[ids,selected]),selected=selected)
        profiles['reference'].append(entry(path,Path('_references')/path.name))
    # De-duplicate target paths across profiles. A dependency belongs to the earliest required profile.
    seen={}
    for profile,items in profiles.items():
        unique=[]
        for item in items:
            if item['path'] in seen:
                if seen[item['path']]!=item['sha256']:raise ValueError('Conflicting target artifact')
                continue
            seen[item['path']]=item['sha256'];unique.append(item)
        profiles[profile]=sorted(unique,key=lambda x:x['path'])
    plan=dict(schema=1,captured_at_utc=capture['captured_at_utc'],capture=capture,profiles=profiles)
    write_json(plan_path,plan)
    write_json(out/'SIZE_SUMMARY.json',{k:dict(files=len(v),bytes=sum(x['bytes'] for x in v)) for k,v in profiles.items()})
    print(json.dumps(dict(phase='plan_complete',profiles=json.loads((out/'SIZE_SUMMARY.json').read_text()))),flush=True)
    return plan

def volumes(items,maximum):
    result=[];current=[];size=10240
    for item in items:
        amount=math.ceil(item['bytes']/512)*512+2048
        if amount>maximum:raise ValueError('One artifact is larger than the volume budget')
        if current and size+amount>maximum:result.append(current);current=[];size=10240
        current.append(item);size+=amount
    if current:result.append(current)
    return result

def main(a):
    out=Path(a.out).resolve();plan=create_plan(Path(a.source),out)
    if a.plan_only:return
    jobs=[]
    for profile in a.profiles.split(',') if a.profiles else plan['profiles']:
        for index,files in enumerate(volumes(plan['profiles'][profile],a.volume_mib*(1<<20))):
            ident=f'{profile}-{index:04d}';jobs.append((profile,ident,files))
    results=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        pending={pool.submit(pack_volume,out/(ident+'.tar'),files,Path('/'),ident):(profile,ident) for profile,ident,files in jobs}
        for future in as_completed(pending):
            profile,ident=pending[future];result=future.result();result['profile']=profile;results.append(result)
            write_json(out/'PACKING_PROGRESS.json',dict(status='PACKING',completed=len(results),total=len(jobs),last=result))
            print(json.dumps(dict(phase='volume_complete',completed=len(results),total=len(jobs),**result)),flush=True)
    manifest=dict(schema=1,repository='IDayday/-recogdrive-representation-teacher-1',
        tag=a.tag,captured_at_utc=plan['captured_at_utc'],capture=plan['capture'],
        profiles={name:dict(files=len(items),bytes=sum(x['bytes'] for x in items)) for name,items in plan['profiles'].items()},
        assets=sorted(results,key=lambda x:x['name']))
    write_json(out/'RELEASE_MANIFEST.json',manifest)
    write_json(out/'PACKING_PROGRESS.json',dict(status='PACK_COMPLETE',volumes=len(results),bytes=sum(x['bytes'] for x in results)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    p.add_argument('--profiles');p.add_argument('--plan-only',action='store_true');p.add_argument('--workers',type=int,default=4)
    p.add_argument('--volume-mib',type=int,default=1536);p.add_argument('--tag',default='continuation-20261022')
    main(p.parse_args())
