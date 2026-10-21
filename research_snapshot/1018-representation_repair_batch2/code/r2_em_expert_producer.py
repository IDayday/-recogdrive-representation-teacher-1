"""Behavior refit after measured assignment changes, with own quality spaces.

The first controlled feedback round covers every K/family/fold at predefined
fit-seed0; finalist recipes must later be replicated with the other two seeds.
This budget rule is independent of the observed score and avoids a single large
method consuming the entire queue before routing methods receive evidence.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced


def main():
    setup('em_behavior_expert_producer')
    import numpy as np
    while not (ROOT/'fullspace_references/COMPLETE.json').exists():time.sleep(15)
    refs={(r['heldout_fold'],r['block']):r for r in read(ROOT/'fullspace_references/COMPLETE.json')['references']}
    train=ROOT/'runs/em_behavior_experts_v1';evaluation=ROOT/'runs/em_behavior_quick_v1'
    for base in [train,evaluation]:
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='feedback_subgroup_behavior_refit',path=str(train.relative_to(ROOT)),handler='code/r2_learned_expert_v3.py',handler_sha256=sha(ROOT/'code/r2_learned_expert_v3.py'),kind='custom',priority=24.8))
    register_once(dict(name='feedback_experts_true_cached_quick_scores',path=str(evaluation.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=23.9))
    protocol=ROOT/'config/EM_BEHAVIOR_REFIT_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),round=1,K=list(range(2,9)),families=['representation','response','correction'],folds=[-1,0,1,2,3,4],
        initial_refit_seed=2026101801,other_fit_seeds='Replicate selected recipes before independent confirmation; original first-round methods already cover all three.',
        spaces=['full','own_group_quality_residual'],sites=['interface_pre','interface_post'],steps=512,checkpoints=[256,512],rank=32,cap=.1,
        training_noise=[0,1,2],retention_weight=2.,new_failure_membership=True,quality_geometry_refitted=True,quick_panel=[32,24,8],validation_fitted=False,test_accessed=False))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);panels={}
    queue=read(train/'tasks.json');known={t['id'] for t in queue};ev_queue=read(evaluation/'tasks.json');ev_known={t['id'] for t in ev_queue};evaluated=set()
    while True:
        changed=False;ev_changed=False;inactive=[]
        spaces={}
        for p in (ROOT/'analysis/expert_spaces').glob('space_learned_em1_*.json'):
            d=read(p);task=d['task'];key=(task['responsibility_meta'],task['expert'],task['cell']['block']);spaces.setdefault(key,[]).append(d)
        for meta_path in sorted((ROOT/'analysis/response_refinement').glob('*/*_em1.json')):
            meta=read(meta_path)
            if meta['fit_seed']!=2026101801:continue
            held=meta['heldout_fold'];system=meta['parent_system'].replace('_K','_em1_K',1);key_path=str(meta_path.relative_to(ROOT))
            for expert in range(meta['K']):
                if meta['effective_counts'][expert]<24 or meta['sessions'][expert]<4:
                    inactive.append(dict(system=system,heldout_fold=held,expert=expert,reason='Insufficient soft effective cases or hard-membership sessions'));continue
                for site in ['interface_pre','interface_post']:
                    candidates=[('full',refs[(held,site)])];fits=spaces.get((key_path,expert,site),[])
                    if len(fits)==2:
                        choices=[f for d in fits for f in d.get('fits',[]) if f['config']['kind'] in ['basis_residual','variance_residual'] and 8<=f['r']<=256]
                        if choices:candidates.append(('subgroup_quality',max(choices,key=lambda f:(f['config']['training_auc'],-f['r']))))
                    for name,fit in candidates:
                        spec=dict(system=system,K=meta['K'],expert=expert,responsibility_meta=key_path,block=site,group='valid_mean',heldout_fold=held,fit_seed=meta['fit_seed'],
                            fit_path=fit['path'],fit_sha256=fit['sha256'],rank=32,cap=.1,space_control='full' if name=='full' else 'subgroup_quality',
                            steps=512,checkpoints=[256,512],learning_rate=.003,edit_penalty=.0001,retention_weight=2.,training_noise_indices=[0,1,2],
                            formation_round=1,parent_system=meta['parent_system'])
                        ident='em_behavior_'+digest(spec)[:24]
                        if ident not in known:enqueue(queue,known,dict(id=ident,**spec));changed=True
        for task in queue:
            path=ROOT/'learned_experts'/task['id']/'TRAINING.json'
            if task['id'] in evaluated or not path.exists():continue
            model=read(path);held=task['heldout_fold']
            if held not in panels:
                mask=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows]);salt=dict(em_expert_quick=20261018,held=held)
                partitions={n:balanced(np.flatnonzero(mask&condition),rows,count,salt) for n,condition,count in [('failure',quality<.7,32),('high',quality>.9,24),('intermediate',(quality>=.7)&(quality<=.9),8)]}
                panels[held]=(sum(partitions.values(),[]),partitions)
            panel,partitions=panels[held];arms=[]
            for checkpoint in model['checkpoints']:
                for strength in [.25,.5,1.]:
                    spec=dict(kind='learned',slot=task['expert'],training_task=task,checkpoint=checkpoint,strength=strength)
                    arms.append(dict(id='em_arm_'+digest(spec)[:24],**spec))
            point=evaluation/'points'/(task['id']+'.json')
            if not point.exists():atomic(point,dict(id=task['id'],task=task,arms=arms,panel=panel,panel_partitions=partitions,seeds=[0,1,2],training_only=True))
            for start in range(0,len(panel),4):enqueue(ev_queue,ev_known,dict(id=task['id']+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(evaluation.relative_to(ROOT))))
            evaluated.add(task['id']);ev_changed=True
        if changed:atomic(train/'tasks.json',queue);atomic(train/'producer.json',dict(complete=False,tasks=len(queue),time=stamp(),inactive=inactive))
        if ev_changed:atomic(evaluation/'tasks.json',ev_queue);atomic(evaluation/'producer.json',dict(complete=False,tasks=len(ev_queue),trained=len(evaluated),time=stamp()))
        time.sleep(60)


if __name__=='__main__':main()
