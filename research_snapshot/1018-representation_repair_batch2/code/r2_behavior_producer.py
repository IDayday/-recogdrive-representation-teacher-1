"""Full expert/fold/seed coverage, with streaming evaluation before routing.

Each K has its own independently formed groups. Neither this producer nor its
quick enriched panels define a final policy or a held-out performance claim.
"""
from r2_common import *
from r2_calibrate_learners import register
from r2_coarse_producer import balanced


def main():
    setup('behavior_expert_producer')
    import numpy as np
    ready=ROOT/'fullspace_references/COMPLETE.json'
    evaluation_smoke=ROOT/'runs/learned_prefetch_eval_pilot_v2/receipts/prefetch_eval_pilot_v2.json'
    while not (ready.exists() and evaluation_smoke.exists()):time.sleep(15)
    assert (ROOT/'runs/learned_prefetch_pilot_v2/receipts/learned_prefetch_noise_pilot_v2.json').exists()
    references={(r['heldout_fold'],r['block']):r for r in read(ready)['references']}
    train=ROOT/'runs/behavior_experts_v1';evaluation=ROOT/'runs/behavior_experts_eval_v1'
    assert not (train/'producer.json').exists();tasks=[];inactive=[]
    for held in [-1,0,1,2,3,4]:
        fold='all' if held<0 else f'fold{held}'
        system_lists=[read(ROOT/'analysis/initial_groups'/fold/'COMPLETE.json')['initialization_systems']]
        for family in ['response','correction']:system_lists.append(read(ROOT/'analysis/outcome_groups'/fold/(family+'_COMPLETE.json'))['initialization_systems'])
        for systems in system_lists:
            for system in systems:
                meta_path=(ROOT/system['path']).with_suffix('.json')
                for expert in range(system['K']):
                    if system['effective_counts'][expert]<24 or system['sessions'][expert]<4:
                        inactive.append(dict(system=system['id'],expert=expert,heldout_fold=held,reason='Insufficient support'));continue
                    for block,steps,checkpoints in [('interface_pre',768,[256,512,768]),('interface_post',512,[128,256,512])]:
                        f=references[(held,block)]
                        spec=dict(system=system['id'],K=system['K'],expert=expert,responsibility_meta=str(meta_path.relative_to(ROOT)),
                             block=block,group='valid_mean',heldout_fold=held,fit_seed=system['fit_seed'],
                             fit_path=f['path'],fit_sha256=f['sha256'],rank=32,cap=.1,space_control='full',
                             steps=steps,checkpoints=checkpoints,learning_rate=.003,edit_penalty=.0001,
                             retention_weight=2.,training_noise_indices=[0,1,2])
                        tasks.append(dict(id='behavior_'+digest(spec)[:24],**spec))
    atomic(train/'tasks.json',tasks);atomic(train/'producer.json',dict(complete=True,tasks=len(tasks),time=stamp(),inactive=inactive))
    atomic(train/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),tasks=len(tasks),systems_per_fold=63,folds=[-1,0,1,2,3,4],
           K=list(range(2,9)),fit_seeds=read(ROOT/'config/execution_v1.json')['fit_seeds'],identity_expert=True,
           sites=['interface_pre','interface_post'],learned_output_rank=32,cap=.1,training_noise_indices=[0,1,2],
           checkpoint_coverage='All stored; earliest and final get the initial broad true-score sweep; midpoint retained for refinement.',
           inactive=inactive,all_label_dependent_training_excludes_heldfold=True,validation_fitted=False,test_accessed=False,
           no_final_effect_claim=True))
    atomic(evaluation/'tasks.json',[]);atomic(evaluation/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register(dict(name='behavior_experts_all_K_folds',path=str(train.relative_to(ROOT)),handler='code/r2_learned_expert_v2.py',
                  handler_sha256=sha(ROOT/'code/r2_learned_expert_v2.py'),kind='custom',priority=25))
    register(dict(name='behavior_expert_streaming_real_scores',path=str(evaluation.relative_to(ROOT)),handler='code/r2_learned_eval.py',
                  handler_sha256=sha(ROOT/'code/r2_learned_eval.py'),kind='custom',priority=24))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows]);panels={}
    for held in [-1,0,1,2,3,4]:
        mask=explore&((folds!=held) if held>=0 else True);salt=dict(behavior_expert_panel=20261018,held=held)
        fail=balanced(np.flatnonzero(mask&(q<.7)),rows,32,salt);high=balanced(np.flatnonzero(mask&(q>.9)),rows,24,salt);mid=balanced(np.flatnonzero(mask&(q>=.7)&(q<=.9)),rows,8,salt)
        panels[held]=(fail+high+mid,dict(failure=fail,high=high,intermediate=mid))
    handled=set();queue=[]
    while len(handled)<len(tasks):
        changed=False
        for task in tasks:
            if task['id'] in handled:continue
            path=ROOT/'learned_experts'/task['id']/'TRAINING.json'
            if not path.exists():continue
            d=read(path);assert len(d['checkpoints'])==3;arms=[]
            for checkpoint in [d['checkpoints'][0],d['checkpoints'][-1]]:
                for strength in [.25,.5,1.]:
                    spec=dict(training_task=task,checkpoint=checkpoint,strength=strength)
                    arms.append(dict(id='behavior_arm_'+digest(spec)[:20],**spec))
            panel,partitions=panels[task['heldout_fold']];point=evaluation/'points'/(task['id']+'.json')
            atomic(point,dict(id=task['id'],task=task,arms=arms,panel=panel,panel_partitions=partitions,seeds=[0,1,2],training_only=True,actual_outcome_cv=False))
            for start in range(0,len(panel),4):
                queue.append(dict(id=task['id']+'_%03d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(evaluation.relative_to(ROOT))))
            handled.add(task['id']);changed=True
        if changed:
            atomic(evaluation/'tasks.json',queue);atomic(evaluation/'producer.json',dict(complete=False,tasks=len(queue),trained=len(handled),expected=len(tasks),time=stamp()))
        if len(handled)<len(tasks):time.sleep(30)
    atomic(evaluation/'producer.json',dict(complete=True,tasks=len(queue),trained=len(handled),expected=len(tasks),time=stamp()))
    print(json.dumps(dict(status='PRODUCED',training_tasks=len(tasks),evaluation_tasks=len(queue))),flush=True)


if __name__=='__main__':main()
