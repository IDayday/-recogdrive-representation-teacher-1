"""Stream complete per-system expert libraries for real feedback and routing.

K counts nonzero repair modules. Safety/PDMS parameterizations are separate
policies; their union is an exploratory response bank, not a hidden 2K policy.
"""
from r2_common import *
from r2_coarse_producer import balanced
from r2_resume_support import register_once as register, enqueue
from collections import defaultdict


def main():
    setup('expert_library_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows])
    path=ROOT/'runs/behavior_experts_v1/tasks.json'
    while not path.exists():time.sleep(15)
    systems=defaultdict(list)
    for task in read(path):systems[(task['heldout_fold'],task['system'])].append(task)
    main_stage=ROOT/'runs/expert_library_S0_v1';noise_stage=ROOT/'runs/expert_library_noise_v1'
    for base in [main_stage,noise_stage]:
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    for name,base,priority in [('expert_library_full_failure_feedback',main_stage,23),('expert_library_noise_transfer',noise_stage,23.5)]:
        register(dict(name=name,path=str(base.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=priority))
    if not (ROOT/'config/EXPERT_LIBRARY_PROTOCOL.json').exists():atomic(ROOT/'config/EXPERT_LIBRARY_PROTOCOL.json',dict(status='FROZEN',time=stamp(),systems=len(systems),
           coverage='Every training-fold S0 failure, 256 training successes, 128 intermediate cases. S1/S2: 256 failures,128 successes,64 intermediate.',
           expert_configuration='One PDMS-priority and one safe-panel proposal per slot; deduplicated union for search only.',
           safety='Collision, offroad and zero-score net counts; TTC and total failures reported separately.',
           routing_must_preserve_K=True,quality_scores_not_deployment_features=True,
           whole_system_cv_pending=True,validation_accessed=False,test_accessed=False))
    panels={};handled=set();queues={b:read(b/'tasks.json') for b in [main_stage,noise_stage]};known={b:{t['id'] for t in q} for b,q in queues.items()}
    while len(handled)<len(systems):
        changed=False
        for key,models in systems.items():
            if key in handled:continue
            held,system=key;folder=ROOT/'analysis/responses/behavior_experts_eval_v1'
            if not all((folder/(m['id']+'.json')).exists() for m in models):continue
            group_meta=read(ROOT/models[0]['responsibility_meta'])
            with np.load(ROOT/group_meta['path']) as z:
                failure_indices=np.array(z['global_indices']);responsibility=np.array(z['responsibility'])
            positions={int(i):j for j,i in enumerate(failure_indices)};candidates=defaultdict(list);reference=None;sample=None
            for m in models:
                response=read(folder/(m['id']+'.json'));point=read(ROOT/response['point'])
                with np.load(ROOT/response['matrix']) as z:scores=np.array(z['scores']);indices=np.array(z['global_indices']);arm_ids=list(z['arm_ids'])
                if reference is None:reference=scores[:,0];sample=indices
                else:assert np.array_equal(reference,scores[:,0]) and np.array_equal(sample,indices)
                weight=np.asarray([responsibility[positions[int(i)],m['expert']] if int(i) in positions else 0. for i in indices])
                assert weight.sum()>0
                arms={a['id']:a for a in point['arms']}
                for j,ident in enumerate(arm_ids[1:],1):
                    after=scores[:,j];delta=after-reference
                    gain=float(np.sum(weight[:,None]*delta[:,:,0])/(weight.sum()*delta.shape[1]))
                    collisions=int(np.count_nonzero(after[:,:,1]<1)-np.count_nonzero(reference[:,:,1]<1))
                    offroad=int(np.count_nonzero(after[:,:,2]<1)-np.count_nonzero(reference[:,:,2]<1))
                    zero=int(np.count_nonzero(after[:,:,0]==0)-np.count_nonzero(reference[:,:,0]==0))
                    a=arms[ident]
                    part=dict(kind='learned',id=ident,slot=m['expert'],training_task=a['training_task'],checkpoint=a['checkpoint'],strength=a['strength'])
                    candidates[m['expert']].append(dict(part=part,own_weighted_gain=gain,net_collision=collisions,net_offroad=offroad,net_zero=zero,
                                                       safe_panel=collisions<=0 and offroad<=0 and zero<=0,source=str((folder/(m['id']+'.json')).relative_to(ROOT))))
            selected={};policies={'PDMS':{},'safety':{}};selection=[]
            for expert,options in sorted(candidates.items()):
                pdms=max(options,key=lambda x:x['own_weighted_gain']);safe=[a for a in options if a['safe_panel']]
                conservative=max(safe,key=lambda x:x['own_weighted_gain']) if safe else min(options,key=lambda x:(max(x['net_collision'],0)+max(x['net_offroad'],0)+max(x['net_zero'],0),-x['own_weighted_gain']))
                for role,value in [('PDMS',pdms),('safety',conservative)]:
                    part=value['part'];selected[part['id']]=part;policies[role][str(expert)]=part['id']
                selection.append(dict(expert=expert,PDMS=pdms,safety=conservative,safe_raw_configuration_available=bool(safe),search_candidates=len(options)))
            if held not in panels:
                train=explore&((folds!=held) if held>=0 else True);salt=dict(expert_library_panel=20261018,held=held)
                f=np.flatnonzero(train&(quality<.7)).tolist();h=balanced(np.flatnonzero(train&(quality>.9)),rows,256,salt);mid=balanced(np.flatnonzero(train&(quality>=.7)&(quality<=.9)),rows,128,salt)
                fnoise=balanced(f,rows,256,salt);hnoise=h[:128];midnoise=mid[:64]
                panels[held]=[(f+h+mid,dict(failure=f,high=h,intermediate=mid)),(fnoise+hnoise+midnoise,dict(failure=fnoise,high=hnoise,intermediate=midnoise))]
            ident='library_'+digest(dict(held=held,system=system))[:24]
            selection_path=ROOT/'analysis/expert_library_selection'/(ident+'.json')
            if selection_path.exists():
                frozen=read(selection_path);selected={p['id']:p for p in frozen['arms']};policies=frozen['policies'];selection=frozen['selection']
            if not selection_path.exists():atomic(selection_path,dict(status='FROZEN_EXPLORATORY_PROPOSALS',time=stamp(),system=system,heldout_fold=held,
                   K=models[0]['K'],policies=policies,selection=selection,arms=list(selected.values()),
                   parameter_selection_only_training_fold=True,actual_full_feedback_pending=True,
                   no_claim_safe_policy_from_raw_panel=True,validation_fitted=False,test_accessed=False))
            for which,base,seeds in [(0,main_stage,[0]),(1,noise_stage,[1,2])]:
                panel,parts=panels[held][which];point=base/'points'/(ident+'.json')
                if not point.exists():atomic(point,dict(id=ident,system=system,K=models[0]['K'],heldout_fold=held,arms=list(selected.values()),
                       panel=panel,panel_partitions=parts,seeds=seeds,policies=policies,selection=str(selection_path.relative_to(ROOT)),
                       training_only=True,actual_outcome_cv=False))
                for start in range(0,len(panel),8):
                    enqueue(queues[base],known[base],dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+8,len(panel)),stage=str(base.relative_to(ROOT))))
            handled.add(key);changed=True
        if changed:
            for base,queue in queues.items():
                atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),systems=len(handled),expected=len(systems),time=stamp()))
        if len(handled)<len(systems):time.sleep(60)
    for base,queue in queues.items():atomic(base/'producer.json',dict(complete=True,tasks=len(queue),systems=len(handled),expected=len(systems),time=stamp()))
    print(json.dumps(dict(status='PRODUCED',systems=len(handled),tasks={b.name:len(q) for b,q in queues.items()})),flush=True)


if __name__=='__main__':main()
