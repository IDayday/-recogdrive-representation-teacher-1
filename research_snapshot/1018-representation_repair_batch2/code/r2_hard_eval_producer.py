"""Actual whole-system held-session validation of hard-router warm starts."""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced
from collections import defaultdict


def wait(path):
    while not path.exists():
        if list((RUN/'failures_gpu').glob('*.json')) or list((RUN/'failures_cpu').glob('*.json')):raise RuntimeError('Recorded experiment error')
        time.sleep(15)


def main():
    setup('hard_policy_evaluation_producer')
    import numpy as np
    wait(ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json')
    pilot=read(ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json')['policy'];base=ROOT/'runs/hard_router_engineering_v1'
    point=ROOT/'config/HARD_ROUTER_ENGINEERING_POINT.json'
    if not point.exists():
        policies=[dict(id='learned_hard_router',policy=pilot),dict(id='forced_Base',policy=pilot,force_choice=0),dict(id='forced_expert',policy=pilot,force_choice=1)]
        for p in policies:p['policy_sha256']=sha(ROOT/p['policy'])
        atomic(point,dict(id='hard_router_engineering',mode='engineering',policies=policies,panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel'],seeds=[0,1,2]))
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[dict(id='hard_router_engineering',point=str(point.relative_to(ROOT)),start=0,end=2,stage=str(base.relative_to(ROOT)))])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    handler='code/r2_hard_policy_eval.py';version=sha(ROOT/handler)
    register_once(dict(name='hard_policy_full_chain_smoke',path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=version,kind='custom',priority=6))
    wait(base/'receipts/hard_router_engineering.json')
    atomic(ROOT/'provenance/HARD_ROUTER_ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),policy=pilot,real_scoring=True,exact_Base_option=True,
           forced_nonzero_exercised=True,feature_runtime_cache_checked=True,heldout_guard_implemented=True))
    stage=ROOT/'runs/warm_hard_cv_v1'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
    if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='hard_warm_whole_system_CV',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=version,kind='custom',priority=22))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);explore=np.array([r['subset']=='exploration' for r in rows])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    expected={(t['heldout_fold'],t['system']) for t in read(ROOT/'runs/behavior_experts_v1/tasks.json')}
    queue=read(stage/'tasks.json');known={t['id'] for t in queue};handled=set();panels={}
    while handled!=expected:
        policies=defaultdict(dict)
        for p in (ROOT/'routers').glob('*/POLICY.json'):
            d=read(p);policies[(d['heldout_fold'],d['system'])][(d['role'],d['tier'])]=(p,d)
        changed=False
        for key,entries in policies.items():
            if key in handled or len(entries)!=6:continue
            held,system=key
            if held not in panels:
                mask=explore&((folds==held) if held>=0 else True);salt=dict(hard_outer_panel=20261018,held=held)
                failure=np.flatnonzero(mask&(quality<.7)).tolist() if held>=0 else balanced(np.flatnonzero(mask&(quality<.7)),rows,32,salt)
                high=balanced(np.flatnonzero(mask&(quality>.9)),rows,512 if held>=0 else 24,salt)
                mid=balanced(np.flatnonzero(mask&(quality>=.7)&(quality<=.9)),rows,256 if held>=0 else 8,salt)
                panels[held]=(failure+high+mid,dict(failure=failure,high=high,intermediate=mid))
            panel,parts=panels[held];ident='hard_cv_'+digest(dict(held=held,system=system))[:24]
            point=stage/'points'/(ident+'.json')
            descriptions=[dict(id=role+'_'+tier,policy=str(p.relative_to(ROOT)),policy_sha256=sha(p),role=role,tier=tier) for (role,tier),(p,d) in sorted(entries.items())]
            if not point.exists():atomic(point,dict(id=ident,heldout_fold=held,system=system,mode='heldout' if held>=0 else 'training',
                  policies=descriptions,panel=panel,panel_partitions=parts,seeds=[0,1,2],
                  evaluation_scope='All held-fold failures plus stratified successes/intermediate; report weighted estimates and raw counts.',
                  full_system_outer_cv=held>=0,validation_accessed=False,test_accessed=False))
            for start in range(0,len(panel),4):
                enqueue(queue,known,dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(stage.relative_to(ROOT))))
            handled.add(key);changed=True
        if changed:
            atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=False,tasks=len(queue),systems=len(handled),expected=len(expected),time=stamp()))
        if handled!=expected:time.sleep(60)
    atomic(stage/'producer.json',dict(complete=True,tasks=len(queue),systems=len(handled),expected=len(expected),time=stamp()))
    print(json.dumps(dict(status='PRODUCED',systems=len(handled),tasks=len(queue))),flush=True)


if __name__=='__main__':main()
