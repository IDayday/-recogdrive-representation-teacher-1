"""Pilot, then elastic joint-policy training and true rescore proposals per system."""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced


def wait(path):
    while not path.exists():time.sleep(15)


def main():
    setup('behavior_router_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    train_handler='code/r2_behavior_router.py';eval_handler='code/r2_behavior_router_eval.py'
    pilot=ROOT/'runs/behavior_router_engineering_v1';pilot_eval=ROOT/'runs/behavior_router_engineering_eval_v1'
    wait(ROOT/'provenance/RESPONSE_LIBRARY_CHAIN_ACCEPTANCE.json')
    selection=None
    while selection is None:
        for p in sorted((ROOT/'analysis/expert_library_selection').glob('*.json')):
            d=read(p)
            if d['heldout_fold']!=-1:continue
            response=[ROOT/'analysis/responses'/name/p.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if all(q.exists() for q in response):selection=(p,d,response);break
        if selection is None:time.sleep(15)
    path,d,response=selection;pilot_tasks=[]
    for kind in ['hard_continuous','soft_joint']:
        ident='joint_router_smoke_'+kind
        pilot_tasks.append(dict(id=ident,selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in response],
            role='PDMS',tier='denoising',kind=kind,fit_seed=2026101801,steps=12,checkpoints=[12],warmup_steps=8))
    if not (pilot/'tasks.json').exists():atomic(pilot/'tasks.json',pilot_tasks);atomic(pilot/'producer.json',dict(complete=True,tasks=len(pilot_tasks),time=stamp()))
    register_once(dict(name='joint_router_training_engineering',path=str(pilot.relative_to(ROOT)),handler=train_handler,handler_sha256=sha(ROOT/train_handler),kind='custom',priority=6))
    for t in pilot_tasks:wait(pilot/'receipts'/(t['id']+'.json'))
    trained=[read(ROOT/'behavior_routers'/t['id']/'TRAINING.json') for t in pilot_tasks]
    smoke_point=pilot_eval/'points/smoke.json';policies=[]
    for model in trained:
        for forced in [False,True]:policies.append(dict(id=model['kind']+('_Base' if forced else ''),model=model,checkpoint=model['checkpoints'][-1],force_Base=forced,identity_threshold=1.01))
    if not smoke_point.exists():atomic(smoke_point,dict(id='joint_router_smoke',mode='engineering',policies=policies,panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel'],seeds=[0,1,2]))
    if not (pilot_eval/'tasks.json').exists():atomic(pilot_eval/'tasks.json',[dict(id='joint_router_eval_smoke',point=str(smoke_point.relative_to(ROOT)),start=0,end=2,stage=str(pilot_eval.relative_to(ROOT)))]);atomic(pilot_eval/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='joint_router_actual_pdms_engineering',path=str(pilot_eval.relative_to(ROOT)),handler=eval_handler,handler_sha256=sha(ROOT/eval_handler),kind='custom',priority=6))
    wait(pilot_eval/'receipts/joint_router_eval_smoke.json')
    atomic(ROOT/'provenance/JOINT_ROUTER_ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),actual_scoring=True,exact_identity=True,hard_continuous_and_soft_joint=True,
        loss_through_actual_denoising=True,no_linear_outcome_assumption=True,pilot_models=[str((ROOT/'behavior_routers'/t['id']/'TRAINING.json').relative_to(ROOT)) for t in pilot_tasks]))
    stage=ROOT/'runs/behavior_router_training_v1';ev=ROOT/'runs/behavior_router_quick_v1'
    for base in [stage,ev]:
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='true_joint_soft_and_continuous_hard_training',path=str(stage.relative_to(ROOT)),handler=train_handler,handler_sha256=sha(ROOT/train_handler),kind='custom',priority=24.7))
    register_once(dict(name='true_joint_policies_actual_training_rescores',path=str(ev.relative_to(ROOT)),handler=eval_handler,handler_sha256=sha(ROOT/eval_handler),kind='custom',priority=23.8))
    protocol=ROOT/'config/BEHAVIOR_ROUTER_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),K=list(range(2,9)),initializations=['representation','response','correction'],fit_seeds=[2026101801,2026101802,2026101803],
        outer_folds=[-1,0,1,2,3,4],kinds=['hard_continuous','soft_joint'],roles=['PDMS','safety'],tiers=['observation','trajectory','denoising'],
        hard_steps=512,soft_steps=768,warmup_steps=128,checkpoints='half/final',
        quick_strength=[.5,1.],identity_threshold=[.5,.9,1.01],quick_panel=dict(failure=32,high=24,intermediate=8),noise=[0,1,2],
        experts_frozen=True,base_frozen=True,continuous_amount_range=[0.,2.],zero_expert=True,
        safety_role_training='safe target, retention multiplier4; safety must be independently verified by real score',
        stage_scope='Training proposals only; full held-fold and independent validation pending.',test_accessed=False))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue};eval_queue=read(ev/'tasks.json');eval_known={t['id'] for t in eval_queue};handled=set();panels={}
    while True:
        changed=False;eval_changed=False
        for p in sorted((ROOT/'analysis/expert_library_selection').glob('*.json')):
            selection=read(p);held=selection['heldout_fold'];responses=[ROOT/'analysis/responses'/name/p.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if not all(q.exists() for q in responses):continue
            for kind in ['hard_continuous','soft_joint']:
                for tier in ['observation','trajectory','denoising']:
                    for role in ['PDMS','safety']:
                        spec=dict(selection=str(p.relative_to(ROOT)),responses=[str(q.relative_to(ROOT)) for q in responses],kind=kind,tier=tier,role=role)
                        ident='joint_router_'+digest(spec)[:24];steps=512 if kind=='hard_continuous' else 768
                        task=dict(id=ident,**spec,steps=steps,checkpoints=[steps//2,steps],warmup_steps=128,retention_weight=4. if role=='safety' else 2.,
                                  fit_seed=2026101801+int(selection['system'].rsplit('seed',1)[1]))
                        if ident not in known:enqueue(queue,known,task);changed=True
                        training_path=ROOT/'behavior_routers'/ident/'TRAINING.json'
                        if ident in handled or not training_path.exists():continue
                        model=read(training_path)
                        if held not in panels:
                            mask=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows]);salt=dict(joint_router_quick=20261018,held=held)
                            parts={n:balanced(np.flatnonzero(mask&condition),rows,count,salt) for n,condition,count in [('failure',quality<.7,32),('high',quality>.9,24),('intermediate',(quality>=.7)&(quality<=.9),8)]}
                            panels[held]=(sum(parts.values(),[]),parts)
                        panel,partitions=panels[held];descriptions=[]
                        for ck in model['checkpoints']:
                            for multiplier in [.5,1.]:
                                for threshold in [.5,.9,1.01]:
                                    config=dict(checkpoint=ck,multiplier=multiplier,identity_threshold=threshold)
                                    descriptions.append(dict(id='joint_config_'+digest(config)[:24],model=model,**config))
                        point=ev/'points'/(ident+'.json')
                        if not point.exists():atomic(point,dict(id=ident,heldout_fold=held,training_only=True,mode='training',policies=descriptions,panel=panel,panel_partitions=partitions,seeds=[0,1,2],training_path=str(training_path.relative_to(ROOT))))
                        for start in range(0,len(panel),4):enqueue(eval_queue,eval_known,dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(ev.relative_to(ROOT))))
                        handled.add(ident);eval_changed=True
        if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=False,tasks=len(queue),time=stamp()))
        if eval_changed:atomic(ev/'tasks.json',eval_queue);atomic(ev/'producer.json',dict(complete=False,tasks=len(eval_queue),models=len(handled),time=stamp()))
        time.sleep(60)


if __name__=='__main__':main()
