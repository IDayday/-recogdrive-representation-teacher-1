"""Single-GPU, configurable-shard first-batch replay and consistent offline teacher export."""
from pathlib import Path
import argparse,csv,gzip,json,os,sys,copy,hashlib,time
import numpy as np
from selector import choose,summarize,FIELDS
from seeds import scene_seed
ROOT=Path(__file__).resolve().parent

def read_rows(cohort,paths):
    with gzip.open(ROOT/f'manifests/{cohort}.csv.gz','rt') as f:rows=list(csv.DictReader(f))
    for r in rows:
        r.update(raw_path=str(Path(paths[cohort+'_logs'])/r['raw_rel']),sensor_root=str(Path(paths[cohort+'_sensor'])/r['sensor_rel']),
                 metric_cache=str(Path(paths[cohort+'_metric'])/r['metric_rel']),cohort=cohort)
    return rows

def bootstrap(paths,out):
    os.environ['RECOGDRIVE_PORTABLE_PATHS']=str(Path(paths).resolve());os.environ['RECOGDRIVE_PORTABLE_WORKDIR']=str(Path(out).resolve()/'runtime')
    import portable_common
    sys.modules['common']=portable_common;portable_common.setup('worker');portable_common.compatibility()
    sys.path.insert(0,str(ROOT/'vendor'))
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features,VISION_GROUPS,LANGUAGE_GROUPS
    from repair_score import score_group
    return Engine(),raw_features,score_group

def gate_open(engine,arm):
    """Original external observation-QDA policy; risk depends on observation, not action noise."""
    gate=arm['observation_gate'];fit=gate['fit'];block=fit['block'];group=fit['group']
    from vlm_core import VISION_GROUPS,LANGUAGE_GROUPS
    matrix,_=engine.vm if block.startswith('vision') else engine.bm if block.startswith('bridge') else engine.lm
    names=VISION_GROUPS if block.startswith(('vision','bridge')) else LANGUAGE_GROUPS
    value=(matrix[names.index(group)]@engine.prefix[block].reshape(-1,engine.prefix[block].shape[-1]).float()).detach().cpu().numpy().astype(np.float64)
    with np.load(ROOT/fit['path']) as z:
        p=(value-z['center'].astype(np.float64))@z['basis'].astype(np.float64);ds=p-z['mh'];df=p-z['mf']
        risk=.5*(ds@z['cov_inv_s'].astype(np.float64)@ds-df@z['cov_inv_f'].astype(np.float64)@df)
    return bool(np.isfinite(risk) and risk>gate['threshold'])

def branch(engine,arm,fits):
    if arm['gate']=='external_observation_qda_hard':
        if not gate_open(engine,arm):return engine.hidden,None,None
        arm=dict(arm,gate='none')
    changed,stat=engine.edited(arm,fits[arm['fit_path']])
    hidden,post=engine.suffix(arm['block'],changed)
    return hidden,post,stat

def main(args):
    if args.cohort=='navtest' and not args.allow_navtest:raise ValueError('navtest needs --allow-navtest; never use it for student training')
    if args.mode=='teacher' and args.cohort=='navtest':raise ValueError('Teacher-training export is limited to navtrain; use historical mode for old navtest diagnostic')
    if not 0<=args.rank<args.world_size:raise ValueError('Invalid configurable shard')
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True);paths=json.loads(args.paths.read_text())
    if args.cache_calibration:
        calibration=json.loads(args.cache_calibration.read_text())
        if calibration['status']!='PASS' or calibration['paths_sha256']!=hashlib.sha256(args.paths.read_bytes()).hexdigest():raise ValueError('Metric-cache calibration does not match local paths')
    catalog=json.loads((ROOT/'configs/methods.json').read_text());rows=read_rows(args.cohort,paths)
    if args.subset!='all':rows=[r for r in rows if r['subset']==args.subset]
    if args.tokens:
        tokens=set(args.tokens.split(','));rows=[r for r in rows if r['token'] in tokens]
    if args.limit:rows=rows[:args.limit]
    rows=rows[args.rank::args.world_size]
    if not rows:raise ValueError('No scenes selected')
    seeds=[int(x) for x in args.seeds.split(',')]
    requested_ids=set(args.methods.split(',')) if args.methods else None
    if requested_ids:catalog=[a for a in catalog if a['id'] in requested_ids]
    if not catalog:raise ValueError('No repair methods')
    from check_assets import check
    if not args.skip_asset_hashes:check(args.paths)
    engine,raw_features,score_group=bootstrap(args.paths,out)
    import torch
    if args.noise_bank:
        from noise_replay import replay_bank
        noise_data=np.load(args.noise_bank,allow_pickle=False);bank_by_seed={}
        for row in rows:
            for j in seeds:
                bank_by_seed[scene_seed(row['token'],j)]=np.array(noise_data[f'{row["token"]}_s{j}'])
        original_trajectory=engine.trajectory
        def explicit_trajectory(features,hidden,value,interface=None):
            with replay_bank(bank_by_seed[value]):return original_trajectory(features,hidden,value,interface)
        engine.trajectory=explicit_trajectory
    fits={}
    for arm in catalog:
        if arm['fit_path'] not in fits:
            with np.load(ROOT/arm['fit_path'],allow_pickle=False) as z:fits[arm['fit_path']]={k:torch.as_tensor(np.array(z[k]),device='cuda',dtype=torch.float32) for k in z.files}
    protocol=dict(mode=args.mode,cohort=args.cohort,subset=args.subset,seeds=seeds,root_seed=20261008,rank=args.rank,world_size=args.world_size,
        methods=[a['id'] for a in catalog],case_fixed=True,teacher_selection=args.teacher_selection,
        source_ids_preserved_but_failure_only_operators_evaluated_on_all_draws=args.mode=='teacher',interface_position='action_head.feature_encoder output [valid_tokens,384]',
        interface_dtype=args.interface_dtype,teacher_min_pdms=args.teacher_min_pdms,planner_runtime=engine.planner_runtime,
        catalog_sha256=hashlib.sha256(json.dumps(catalog,sort_keys=True).encode()).hexdigest(),checkpoint_sha256=engine.cfg['checkpoint_sha256'],
        explicit_noise_bank_sha256=hashlib.sha256(args.noise_bank.read_bytes()).hexdigest() if args.noise_bank else None)
    protocol['cache_calibration_sha256']=hashlib.sha256(args.cache_calibration.read_bytes()).hexdigest() if args.cache_calibration else None
    semantic_protocol={k:v for k,v in protocol.items() if k not in ['planner_runtime','rank','world_size']}
    protocol_hash=hashlib.sha256(json.dumps(semantic_protocol,sort_keys=True).encode()).hexdigest()
    (out/f'protocol_rank{args.rank:03d}.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    began=time.monotonic();done=0
    for row in rows:
        dest=out/'cases'/row['token'];dest.mkdir(parents=True,exist_ok=True)
        marker=dest/'COMPLETE.json'
        if marker.exists():
            prev=json.loads(marker.read_text())
            if prev['protocol_sha256']!=protocol_hash:raise ValueError('Output protocol differs; choose a new directory')
            done+=1;continue
        with torch.no_grad():
            features=raw_features(row);native=engine.forward_native(features)
            base_preds=np.stack([engine.trajectory(features,native,scene_seed(row['token'],j)).float().cpu().numpy() for j in seeds])
            predictions=[base_preds];edits=[]
            for arm in catalog:
                hidden,post,stat=branch(engine,arm,fits)
                values=np.stack([engine.trajectory(features,hidden,scene_seed(row['token'],j),post).float().cpu().numpy() for j in seeds])
                predictions.append(values);edits.append(stat.detach().float().cpu().numpy().tolist() if stat is not None else [0,0,0,0])
            trajectories=np.stack(predictions,axis=1)
        metric_sha=row['metric_sha256']
        if args.cache_calibration:
            from portable_common import sha
            metric_sha=sha(row['metric_cache'])
        scoring=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=metric_sha,scoring=engine.cfg['scoring'],
            records=[dict(trajectory=trajectories[j,k].tolist(),seed_index=seed,arm=k) for j,seed in enumerate(seeds) for k in range(len(catalog)+1)]))
        scores=np.array([[r['score'][f] for f in FIELDS] for r in scoring]).reshape(len(seeds),len(catalog)+1,7)
        if args.mode=='historical':
            failed=scores[:,0,0]<.7
            for k,arm in enumerate(catalog,1):
                if arm['historical_external_failure_only']:
                    scores[~failed,k]=scores[~failed,0];trajectories[~failed,k]=trajectories[~failed,0]
            selection_mode='historical_failure_only'
        else:selection_mode=args.teacher_selection
        index,selected=choose(scores[:,None,:,:],selection_mode);k=int(index[0]);selected=selected[:,0]
        chosen_predictions=trajectories[:,k].copy()
        if args.mode=='historical':chosen_predictions[scores[:,0,0]>=.7]=base_preds[scores[:,0,0]>=.7]
        eligible=bool((selected[:,0]>args.teacher_min_pdms/100).all())
        interface_file=None;quantization_max_error=None
        if args.mode=='teacher' and eligible:
            with torch.no_grad():
                if k:condition,post,_=branch(engine,catalog[k-1],fits)
                else:condition,post=native,None
                replay=np.stack([engine.trajectory(features,condition,scene_seed(row['token'],j),post).float().cpu().numpy() for j in seeds])
                if not np.array_equal(replay,chosen_predictions):raise AssertionError('Selected branch replay changed trajectories')
                interface=post if post is not None else engine.agent.action_head.feature_encoder(condition)
                full=interface[0].float().cpu().numpy();attention=engine.inputs['attention_mask'][0].detach().cpu().numpy().astype(bool)
                token_ids=engine.inputs['input_ids'][0].detach().cpu().numpy();target=full[attention]
                saved=target.astype(args.interface_dtype);quantization_max_error=float(np.max(np.abs(saved.astype(np.float32)-target)))
                interface_file='teacher_interface.npz';np.savez_compressed(dest/interface_file,interface=saved,token_ids=token_ids[attention],attention_mask=attention,original_shape=np.array(full.shape))
        np.savez_compressed(dest/'branches.npz',scores=scores,trajectories=trajectories,selected_method_index=np.array(k),selected_scores=selected,selected_trajectories=chosen_predictions,seeds=np.array(seeds),integer_seeds=np.array([scene_seed(row['token'],j) for j in seeds]),edit_stats=np.array(edits))
        result=dict(status='COMPLETE',token=row['token'],session=row['session'],subset=row['subset'],protocol_sha256=protocol_hash,selection_mode=selection_mode,
            selected_method='baseline' if k==0 else catalog[k-1]['id'],teacher_eligible=eligible,interface_file=interface_file,interface_quantization_max_abs_error=quantization_max_error,
            base_pdms=(scores[:,0,0]*100).tolist(),teacher_pdms=(selected[:,0]*100).tolist(),per_scene_actual_branch_shared_across_seeds=args.mode=='teacher')
        result.update(metric_sha256=metric_sha,original_metric_sha256=row['metric_sha256'])
        marker.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');done+=1
        engine.verify_engine();status=dict(status='RUNNING',rank=args.rank,completed=done,total=len(rows),elapsed_seconds=time.monotonic()-began)
        (out/f'status_rank{args.rank:03d}.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    (out/f'COMPLETE_rank{args.rank:03d}.json').write_text(json.dumps(dict(status='COMPLETE',scenes=done,protocol_sha256=protocol_hash))+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',type=Path,required=True);p.add_argument('--out',required=True);p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain');p.add_argument('--subset',default='exploration');p.add_argument('--mode',choices=['historical','teacher'],default='teacher')
    p.add_argument('--allow-navtest',action='store_true');p.add_argument('--seeds',default='0,1,2,3,4');p.add_argument('--rank',type=int,default=0);p.add_argument('--world-size',type=int,default=1);p.add_argument('--limit',type=int);p.add_argument('--tokens');p.add_argument('--methods');p.add_argument('--skip-asset-hashes',action='store_true');p.add_argument('--noise-bank',type=Path);p.add_argument('--cache-calibration',type=Path)
    p.add_argument('--teacher-selection',choices=['teacher_safe','teacher_consistent'],default='teacher_safe');p.add_argument('--teacher-min-pdms',type=float,default=90);p.add_argument('--interface-dtype',choices=['float32','float16'],default='float32');main(p.parse_args())
