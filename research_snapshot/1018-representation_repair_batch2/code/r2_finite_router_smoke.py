"""Intercept original warm parameters, then verify actual fixed-action reuse."""
from r2_common import *


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_behavior_router_v2_nativecache import run as original
    from r2_finite_router import run as train
    from r2_finite_router_predict import run as predict
    from r2_library_rollouts import load,apply,block
    from r2_cached_interfaces import from_cached
    from r2_eval_rollouts import Fits
    from repair_score import score_group
    source=task['source'];captured=[];counter=[0];old_step=torch.optim.AdamW.step
    class CapturedWarm(Exception):pass
    def observe(optimizer,*args,**kwargs):
        value=old_step(optimizer,*args,**kwargs);counter[0]+=1
        if counter[0]==128:
            captured.extend(p.detach().cpu().numpy().copy() for group in optimizer.param_groups for p in group['params']);raise CapturedWarm()
        return value
    torch.optim.AdamW.step=observe
    try:
        try:original(engine,dict(source,id='finite_original_warm_observer_v1'),pool)
        except CapturedWarm:pass
    finally:torch.optim.AdamW.step=old_step
    assert counter[0]==128 and captured
    models=[];reports=[]
    for method in ['ce_continuation','regret_uniform','regret_natural']:
        spec=dict(id='finite_engineering_'+method,selection=source['selection'],responses=source['responses'],role=source['role'],tier=source['tier'],fit_seed=source['fit_seed'],
            steps=160,warmup_steps=128,checkpoints=[128,160],original_proxy_steps=source['steps'],method=method,science_phase='engineering')
        result=train(engine,spec,pool);model=read(ROOT/result['path']);models.append(model)
        with np.load(ROOT/model['checkpoints'][0]['path']) as z:
            assert len(z.files)==len(captured)
            for name,value in zip(z.files,captured):assert np.array_equal(z[name],value),(method,name)
        reports.append(dict(method=method,warm128_arrays_exact=True,trace=model['trace']))
    bank=read(ROOT/task['bank'])
    with np.load(ROOT/bank['matrix']) as z:indices=np.array(z['global_indices']);panel=indices[:2].tolist()
    policies=[dict(id='finite_'+m['method'],model=m,checkpoint=m['checkpoints'][-1]) for m in models]
    policies += [dict(policies[0],id='finite_forced_Base',force_Base=True),dict(policies[0],id='finite_forced_expert',force_choice=1)]
    point=ROOT/task['stage']/'points/smoke.json';atomic(point,dict(id='finite_engineering',mode='engineering',heldout_fold=-1,bank=task['bank'],system=bank['system'],policies=policies,panel=panel,seeds=[0,1,2]))
    predicted=predict(engine,dict(id=task['id']+'_prediction',stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=len(panel)),pool);actual=read(ROOT/predicted['path']);fits=Fits();compared=0
    for index in panel:
        row,features,reference=load(index,engine.cfg,True)
        with torch.no_grad():
            hidden=from_cached(engine,features,index)
            for record in [r for r in actual['records'] if r['token']==row['token']]:
                if record['arm']=='baseline' or record.get('choice')==0:condition,post=hidden,None
                else:
                    policy=next(p for p in policies if p['id']==record['arm']);part=policy['model']['parts'][record['choice']-1];changed,_=apply(engine,part,fits);condition,post=engine.suffix(block(part),changed)
                trajectory=engine.trajectory(features,condition,seed(row['token'],record['seed_index']),post)
                assert np.array_equal(trajectory.cpu().numpy(),np.asarray(record['trajectory'],dtype=np.float32));compared+=1
        records=[r for r in actual['records'] if r['token']==row['token']];scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=[{k:v for k,v in r.items() if k!='score'} for r in records])).result(timeout=3600)
        for a,b in zip(records,scored):assert a['score']==b['score']
    engine.verify_engine();path=ROOT/'provenance/FINITE_OUTCOME_ROUTER_ENGINEERING_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),original_frozen_trainer_intercepted_after_warm_steps=128,original_source='code/r2_behavior_router_v2_nativecache.py',original_source_sha256=sha(ROOT/'code/r2_behavior_router_v2_nativecache.py'),
        all_three_warm_checkpoints_bitwise_exact=True,training=reports,cached_candidate_choices_regenerated_and_independently_scored=compared,
        actual_prediction=predicted,exact_Base_and_nonzero_forced_controls=True,no_GT_proxy_after_warm=True,Base_experts_frozen=True,
        scope='Engineering only, all-training artifacts; expected utility concerns choosing an independent whole candidate, not blending hidden-state effects.'))
    return dict(path=str(path.relative_to(ROOT)),records_exact=compared)
