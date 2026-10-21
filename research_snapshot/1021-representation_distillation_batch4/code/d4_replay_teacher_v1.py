"""Replay the fixed R2 branch, export full context, require bit-exact history.

No teacher selection, GT target, augmentation, or alternative candidate search.
The valid-token target, all five trajectories, and fresh scores must equal the
first42 snapshot. The new full interface comes from this same actual execution.
"""
from d4_common import *
from functools import lru_cache

BANK=None


@lru_cache(maxsize=2)
def sources(path,hashed):
    assert sha(path)==hashed
    return read(path)


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from repair_score import score_group
    from r3_runtime import prediction
    from r3_first42_rollout_v2 import FitBank,observation_gate
    from r3_incremental_audit_v1 import FIELDS
    global BANK
    if BANK is None:BANK=FitBank()
    scenes=sources(task['scenes'],task['scenes_sha256']);pack=sources(task['pack'],task['pack_sha256'])
    by_id={e['id']:e for e in pack['entries']};outputs=[];began=time.monotonic()
    assert engine.planner_runtime['checkpoint_sha256']==pack['checkpoint_sha256']
    for index in task['indices']:
        row=scenes[index];assert index==row['global_index']
        output=ROOT/task['output_stage']/'cases'/row['token'];record=output/'RESULT.json'
        if record.exists():
            old=read(record);assert old['status']=='PASS_EXACT_R2_FULL_CONTEXT_REPLAY'
            assert sha(ROOT/old['arrays']['path'])==old['arrays']['sha256']
            outputs.append(dict(global_index=index,path=str(record.relative_to(ROOT)),sha256=sha(record),resumed=True));continue
        historical_path=B3/row['source_record'];assert sha(historical_path)==row['source_record_sha256']
        historical=read(historical_path);entry=by_id[row['teacher_candidate']]
        assert historical['selection']['R2']==[dict(arm=entry['id'],seed_index=j) for j in range(5)]
        lookup={(r['arm'],r['seed_index']):r for r in historical['records']}
        old_interface_path=B3/row['source_interfaces'];assert sha(old_interface_path)==row['source_interfaces_sha256']
        features=raw_features(row)
        with torch.no_grad(),torch.autocast('cuda',enabled=False):
            hidden=engine.forward_native(features);base_h=engine.prefix['interface_post']
            arm=entry['arm'];condition,post=hidden,None
            if arm is not None:
                actual=arm
                if arm['gate']=='external_observation_qda_hard':
                    active,_=observation_gate(engine,entry['root'],arm)
                    actual=dict(arm,gate='none') if active else None
                if actual is not None:
                    changed,_=engine.edited(actual,BANK.get(entry['root'],actual));condition,post=engine.suffix(actual['block'],changed)
            trajectories=[];interface=None
            for j in range(5):
                trajectory,h=prediction(engine,features,condition,j,row['token'],post)
                if interface is None:interface=h
                else:assert torch.equal(h,interface),'R2 upstream interface changed with noise'
                trajectories.append(trajectory)
            values=torch.stack(trajectories).float().cpu().numpy();full_h=interface[0].float().cpu().numpy()
            ids=engine.inputs['input_ids'][0].cpu().numpy();attention=engine.inputs['attention_mask'][0].cpu().numpy()
            positions=engine.inputs['position_ids'][0].cpu().numpy();valid=np.flatnonzero(attention)
            assert full_h.shape==(len(ids),384) and len(ids)>=2800 and np.isfinite(full_h).all()
            with np.load(old_interface_path,allow_pickle=False) as z:
                assert np.array_equal(ids,z['input_ids']) and np.array_equal(valid,z['valid_token_positions'])
                for j in range(5):
                    old=lookup[entry['id'],j];assert np.array_equal(values[j],np.asarray(old['trajectory'],dtype=np.float32))
                    assert np.array_equal(full_h[valid],z[old['interface_sha256']])
            residual_squared_sum=float((interface-base_h).square().sum().cpu())
            base_squared_sum=float(base_h.square().sum().cpu())
        records=[dict(arm=entry['id'],seed_index=j,seed=seed(row['token'],j),trajectory=values[j].tolist()) for j in range(5)]
        fresh=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=historical['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=3600)
        for r in fresh:assert r['score']==lookup[entry['id'],r['seed_index']]['score']
        quality=np.asarray([[lookup[entry['id'],j]['score'][f] for f in FIELDS] for j in range(5)],dtype=np.float64)
        arrays=output/'full_context.npz'
        hashed=save_arrays(arrays,dict(teacher_interface=full_h,teacher_trajectories=values,teacher_quality=quality,
            input_ids=ids,attention_mask=attention,position_ids=positions,valid_token_positions=valid))
        proof=dict(status='PASS_EXACT_R2_FULL_CONTEXT_REPLAY',time=stamp(),global_index=index,token=row['token'],session=row['session'],subset=row['subset'],pool=row['pool'],
            candidate=entry['id'],source_record=row['source_record'],source_record_sha256=row['source_record_sha256'],source_interfaces_sha256=row['source_interfaces_sha256'],
            arrays=dict(path=str(arrays.relative_to(ROOT)),sha256=hashed),full_tokens=len(ids),valid_tokens=len(valid),padding_tokens=int((attention==0).sum()),
            teacher_interface_sha256=hashlib.sha256(full_h.tobytes()).hexdigest(),teacher_residual_squared_sum=residual_squared_sum,Base_interface_squared_sum=base_squared_sum,
            same_execution_interface=True,all_five_trajectories_exact=True,all_five_fresh_scores_exact=True,valid_interface_exact=True,
            teacher_fixed_not_reselected=True,GT_used=False,scene_manifest_sha256=task['scenes_sha256'],pack_sha256=task['pack_sha256'])
        atomic(record,proof);outputs.append(dict(global_index=index,path=str(record.relative_to(ROOT)),sha256=sha(record)))
    engine.verify_engine()
    result=ROOT/task['output_stage']/'results'/(task['id']+'.json')
    atomic(result,dict(status='COMPLETE_FULL_CONTEXT_REPLAY',time=stamp(),cases=outputs,task=task,seconds=time.monotonic()-began))
    return dict(path=str(result),sha256=sha(result),cases=len(outputs),seconds=time.monotonic()-began)


def smoke():
    import socket
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    setup('teacher_replay_smoke_v1');compatibility()
    import torch
    import psutil
    from vlm_intervene_v4 import Engine
    from r3_runtime import init_scorer
    preflight=dict(time=stamp(),hostname=socket.gethostname(),devices=torch.cuda.device_count(),device_name=torch.cuda.get_device_name(0),
        gpu_free_bytes=torch.cuda.mem_get_info()[0],host_available_bytes=psutil.virtual_memory().available,cpu_affinity=len(os.sched_getaffinity(0)))
    assert preflight['devices']==1 and preflight['gpu_free_bytes']>70*(1<<30) and preflight['host_available_bytes']>30*(1<<30)
    atomic(ROOT/'provenance/DSW_REPLAY_PREFLIGHT_V1.json',preflight)
    path=ROOT/'manifests/R2_SCENES_V1.json';pack=B3/'teachers/first42_v1/PACK.json'
    task=dict(id='teacher_replay_smoke_v1',output_stage='runs/teacher_replay_smoke_v1',indices=read(ROOT/'manifests/SMOKE_INDICES_V1.json'),scenes=str(path),scenes_sha256=sha(path),pack=str(pack),pack_sha256=sha(pack))
    engine=Engine()
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:result=run(engine,task,pool)
    atomic(ROOT/'provenance/TEACHER_REPLAY_SMOKE_V1.json',dict(status='PASS_R2_FULL_CONTEXT_SMOKE',time=stamp(),result=result,task=task,preflight=preflight))
    print(json.dumps(dict(status='PASS_R2_FULL_CONTEXT_SMOKE',cases=result['cases'])),flush=True)


if __name__=='__main__':smoke()
