"""Five matched capacity structures, observable-only routes, one bounded fold.

All larger expert checkpoints already exist. Frozen mathematical programs are
reused; only private manifests, output namespaces and orchestration are new.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue,append_once
from r2_coarse_producer import balanced

REDUCTIONS=set()


def stage(name,handler,priority=24.,enabled=False):
    base=ROOT/'runs'/name
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,time=stamp(),tasks=0))
    register_once(dict(name=name,path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=priority,enabled=enabled))
    return base


def publish(base,tasks,complete=True):
    existing=read(base/'tasks.json');assert not existing or existing==tasks
    if not existing:atomic(base/'tasks.json',tasks);atomic(base/'producer.json',dict(time=stamp(),complete=complete,tasks=len(tasks)))


def chunks(base,point,size=4):
    d=read(point)
    return [dict(id=d['id']+'_%04d'%start,stage=str(base.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=start,end=min(start+size,len(d['panel']))) for start in range(0,len(d['panel']),size)]


def reduce(work,base,point,handler):
    key=(str(base),str(point))
    if key in REDUCTIONS:return
    tasks=chunks(base,point)
    if all((base/'receipts'/(t['id']+'.json')).exists() for t in tasks):
        work.append(dict(id='outcome_capobs_matrix_'+digest(dict(stage=str(base),point=str(point)))[:24],handler=handler,handler_sha256=sha(ROOT/handler),stage=str(base.relative_to(ROOT)),point=str(point.relative_to(ROOT)),chunks=[t['id'] for t in tasks]))
        REDUCTIONS.add(key)


def main():
    setup('capacity_observable_producer')
    import numpy as np
    protocolpath='config/CAPACITY_OBSERVABLE_PILOT_PROTOCOL_V1.json';protocol=read(ROOT/protocolpath);protocolsha=sha(ROOT/protocolpath)
    workflow='code/r2_capacity_observable_workflow.py';workflowsha=sha(ROOT/workflow)
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows]);train=explore&(fold!=0)
    originalbank=read(ROOT/'expert_capacity_controls/banks/COMPLETE.json');allparts={p['id']:p for p in originalbank['parts']};bybank={b['id']:b for b in originalbank['banks']};selections={};union={}
    for v in protocol['variants']:
        b=bybank[v['id']];assert sha(ROOT/b['path'])==b['sha256'];policies={role:{str(j):ident for j,ident in enumerate(b['policies'][role])} for role in ['PDMS','safety']};own={ident:allparts[ident] for ids in b['policies'].values() for ident in ids}
        for ident,p in own.items():assert p['slot'] in [0,1,2] and p['training_task']['rank']==v['rank'];union[ident]=p
        path=ROOT/'expert_capacity_observable/selections'/(v['id']+'.json')
        if not path.exists():atomic(path,dict(status='TRAINING_LOCKED_CAPACITY_CANDIDATES',time=stamp(),system=v['system'],heldout_fold=0,K=3,policies=policies,arms=list(own.values()),source_bank=b,parameter_selection_only_training_fold=True,validation_fitted=False,test_accessed=False))
        selections[v['id']]=path
    feedback=stage('capacity_observable_feedback_S0_v1','code/r2_library_rollouts.py');noise=stage('capacity_observable_feedback_noise_v1','code/r2_library_rollouts.py');salt=dict(expert_library_panel=20261018,held=0)
    failure=np.flatnonzero(train&(q<.7)).tolist();high=balanced(np.flatnonzero(train&(q>.9)),rows,256,salt);middle=balanced(np.flatnonzero(train&(q>=.7)&(q<=.9)),rows,128,salt)
    noise_f=balanced(failure,rows,256,salt);panels=[(feedback,[0],dict(failure=failure,high=high,intermediate=middle)),(noise,[1,2],dict(failure=noise_f,high=high[:128],intermediate=middle[:64]))];responses=[]
    for base,seeds,parts in panels:
        point=base/'points/capacity_observable_train_union.json'
        if not point.exists():atomic(point,dict(id='capacity_observable_train_union',system='capacity_observable_union_not_a_policy',K=3,heldout_fold=0,arms=list(union.values()),panel=sum(parts.values(),[]),panel_partitions=parts,seeds=seeds,training_only=True,actual_outcome_cv=False,own_K_required=True))
        publish(base,chunks(base,point));responses.append('analysis/responses/'+base.name+'/'+point.stem+'.json')
    smoke=stage('capacity_observable_joint_training_smoke_v1','code/r2_native_joint_bridge.py',8,True);smokeeval=stage('capacity_observable_joint_eval_smoke_v1','code/r2_behavior_router_eval.py',8,True)
    joint=stage('capacity_observable_joint_training_v1','code/r2_native_joint_bridge.py');quick=stage('capacity_observable_joint_quick_v1','code/r2_joint_eval_memo_v2.py')
    heldstages={k:stage('capacity_observable_held_'+k+'_v1',h,22.) for k,h in [('hard','code/r2_hard_policy_eval.py'),('candidate','code/r2_candidate_eval.py'),('joint','code/r2_behavior_router_eval.py')]}
    qparts={name:balanced(np.flatnonzero(train&condition),rows,count,dict(joint_router_quick=20261018,held=0)) for name,condition,count in [('failure',q<.7,32),('high',q>.9,24),('intermediate',(q>=.7)&(q<=.9),8)]};quickpanel=sum(qparts.values(),[])
    smoke_tasks=[];formal=[];discrete=[]
    for v in protocol['variants']:
        selection=str(selections[v['id']].relative_to(ROOT))
        for role in ['PDMS','safety']:
            for tier in ['observation','trajectory','denoising']:
                for kind in ['hard_continuous','soft_joint']:
                    steps=512 if kind=='hard_continuous' else 768;spec=dict(selection=selection,responses=responses,kind=kind,tier=tier,role=role,steps=steps,checkpoints=[steps//2,steps],warmup_steps=128,retention_weight=4. if role=='safety' else 2.,fit_seed=2026101801)
                    formal.append(dict(id='capobs_joint_'+digest(spec)[:24],**spec))
                for method,handler in [('hard','code/r2_capacity_observable_hard_fit.py'),('candidate','code/r2_capacity_observable_candidate_fit.py')]:
                    if method=='candidate' and tier=='observation':continue
                    spec=dict(selection=selection,responses=responses,role=role,tier=tier)
                    discrete.append(dict(id='outcome_capobs_'+method+'_'+digest(spec)[:24],handler=handler,handler_sha256=sha(ROOT/handler),**spec))
        if v['id'] in ['capacity_r128_b1','capacity_r256_b1']:
            for kind in ['hard_continuous','soft_joint']:
                spec=dict(selection=selection,responses=responses,kind=kind,tier='trajectory',role='safety',steps=8,checkpoints=[8],warmup_steps=8,retention_weight=4.,fit_seed=2026101801)
                smoke_tasks.append(dict(id='capobs_smoke_'+digest(spec)[:24],**spec))
    assert len(formal)==60 and len(discrete)==50 and len(smoke_tasks)==4
    qq=read(quick/'tasks.json');known={t['id'] for t in qq};prepared=set();analysis_queued=False;discrete_queued=False;first_feedback=None
    while True:
        assert sha(ROOT/protocolpath)==protocolsha and sha(ROOT/workflow)==workflowsha;work=[]
        for base,_,_ in panels:reduce(work,base,base/'points/capacity_observable_train_union.json','code/r2_point_response_v2.py')
        ready=all((ROOT/p).exists() for p in responses)
        if ready:
            if not discrete_queued:append_once('cpu',discrete);discrete_queued=True
            publish(smoke,smoke_tasks)
        smokemodels=[ROOT/'behavior_routers'/t['id']/'TRAINING.json' for t in smoke_tasks]
        if ready and all(p.exists() for p in smokemodels):
            point=smokeeval/'points/capacity_observable_joint_smoke.json';policies=[]
            for path in smokemodels:
                m=read(path)
                for force in [False,True]:policies.append(dict(id=m['task']['id']+('_Base' if force else '_natural'),model=m,checkpoint=m['checkpoints'][-1],force_Base=force,identity_threshold=1.01))
            if not point.exists():atomic(point,dict(id='capacity_observable_joint_smoke',mode='engineering',policies=policies,panel=[qparts['failure'][0],qparts['high'][0]],seeds=[0,1,2]))
            tasks=chunks(smokeeval,point);publish(smokeeval,tasks)
            if (smokeeval/'receipts'/(tasks[0]['id']+'.json')).exists() and not (ROOT/'provenance/CAPACITY_OBSERVABLE_JOINT_ENGINEERING_PASS.json').exists():
                work.append(dict(id='outcome_capobs_joint_engineering_acceptance_v1',handler=workflow,handler_sha256=workflowsha,mode='engineering',stage=str(smokeeval.relative_to(ROOT)),receipt=tasks[0]['id']+'.json',models=[str(p.relative_to(ROOT)) for p in smokemodels]))
        if (ROOT/'provenance/CAPACITY_OBSERVABLE_JOINT_ENGINEERING_PASS.json').exists():publish(joint,formal)
        changed=False
        for t in formal:
            mp=ROOT/'behavior_routers'/t['id']/'TRAINING.json'
            if not mp.exists():continue
            m=read(mp);point=quick/'points'/(t['id']+'.json')
            if t['id'] not in prepared:
                configs=[]
                for ck in m['checkpoints']:
                    for multiplier in [.5,1.]:
                        for threshold in [.5,.9,1.01]:
                            spec=dict(checkpoint=ck,multiplier=multiplier,identity_threshold=threshold);configs.append(dict(id='capobs_joint_config_'+digest(spec)[:24],model=m,**spec))
                if not point.exists():atomic(point,dict(id=t['id'],heldout_fold=0,system=m['system'],training_only=True,mode='training',policies=configs,panel=quickpanel,panel_partitions=qparts,seeds=[0,1,2],training_path=str(mp.relative_to(ROOT))))
                for item in chunks(quick,point):enqueue(qq,known,item)
                prepared.add(t['id']);changed=True
            reduce(work,quick,point,'code/r2_policy_response.py')
            rp=ROOT/'analysis/responses'/quick.name/(t['id']+'.json');policy=ROOT/'expert_capacity_observable/joint_policies'/(t['id']+'.json')
            if rp.exists() and not policy.exists():work.append(dict(id='outcome_capobs_calibration_'+t['id'],handler=workflow,handler_sha256=workflowsha,mode='calibrate',response=str(rp.relative_to(ROOT))))
        if changed:atomic(quick/'tasks.json',qq);atomic(quick/'producer.json',dict(time=stamp(),complete=len(prepared)==60,tasks=len(qq),models_ready=len(prepared)))
        for method,base in heldstages.items():
            paths=[];metadata={};policies=[]
            source_tasks=formal if method=='joint' else [t for t in discrete if t['id'].startswith('outcome_capobs_'+method+'_')]
            for t in source_tasks:
                if method=='joint':path=ROOT/'expert_capacity_observable/joint_policies'/(t['id']+'.json')
                else:path=ROOT/'expert_capacity_observable'/('hard_routers' if method=='hard' else 'candidate_selectors')/t['id']/'POLICY.json'
                paths.append(path)
            if not all(p.exists() for p in paths):continue
            for path in paths:
                d=read(path);v=next(v for v in protocol['variants'] if d['system']==v['system']);label=('joint_'+d['kind']) if method=='joint' else method;ident=v['id']+'__'+label+'__'+d['role']+'_'+d['tier']
                metadata[ident]=dict(variant=v['id'],method=label,role=d['role'],tier=d['tier'],source_policy=str(path.relative_to(ROOT)),source_policy_sha256=sha(path))
                policies.append(dict(d['configuration'],id=ident) if method=='joint' else dict(id=ident,policy=str(path.relative_to(ROOT)),policy_sha256=sha(path)))
            original=read(ROOT/'runs/expert_capacity_held_v1/points/capacity_held_union.json');point=base/'points'/('capacity_observable_held_'+method+'.json')
            if not point.exists():atomic(point,dict(id='capacity_observable_held_'+method,mode='heldout',heldout_fold=0,policies=policies,policy_metadata=metadata,panel=original['panel'],seeds=[0,1,2],single_exploration_fold=True,validation_accessed=False,test_accessed=False))
            publish(base,chunks(base,point));reduce(work,base,point,'code/r2_policy_response.py')
        heldresponses=['analysis/responses/'+base.name+'/capacity_observable_held_'+method+'.json' for method,base in heldstages.items()]
        if not analysis_queued and all((ROOT/p).exists() for p in heldresponses):
            work.append(dict(id='outcome_capobs_complete_diagnostic_v1',handler=workflow,handler_sha256=workflowsha,mode='analyze',protocol=protocolpath,responses=heldresponses));analysis_queued=True
        if work:append_once('cpu',work)
        phase=ROOT/'analysis/expert_capacity_observable/FIVE_MINUTE_PHASE_READY.json'
        if first_feedback is None:
            first=next((feedback/'receipts').glob('*.json'),None)
            if first is not None:first_feedback=read(first)['time']
        if first_feedback and not phase.exists() and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(first_feedback)).total_seconds()>=300:
            atomic(phase,dict(time=stamp(),first_observed_feedback_receipt=first_feedback,mechanical_phase_check_only=True))
        atomic(ROOT/'analysis/expert_capacity_observable/PRODUCER.json',dict(time=stamp(),feedback_ready=ready,joint_engineering=(ROOT/'provenance/CAPACITY_OBSERVABLE_JOINT_ENGINEERING_PASS.json').exists(),formal_joint_models_ready=len(prepared),formal_joint_models_required=60,discrete_policy_models_required=50,held_response_matrices_ready=sum((ROOT/p).exists() for p in heldresponses),analysis_queued=analysis_queued,single_exploration_fold_only=True))
        if (ROOT/'analysis/expert_capacity_observable/SUMMARY.json').exists():return
        time.sleep(30)


if __name__=='__main__':main()
