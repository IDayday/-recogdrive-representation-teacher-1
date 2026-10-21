"""Hierarchical true-outcome probes for each new family and CV-specific expert.

Breadth is retained across all layers. Each broad probe is deliberately small;
promising and complementary regions must receive wider, cross-noise evaluation.
It cannot be reported as a confirmed subgroup effect or final CV policy score.
"""
from r2_common import *
from r2_coarse_producer import balanced
from r2_resume_support import register_once as register, enqueue


def main():
    setup('hierarchical_probe_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    explore=np.array([r['subset']=='exploration' for r in rows]);pools={};panels={};memberships={}
    base=ROOT/'runs/fold_and_outcome_probes_v1'
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    if not (base/'PROTOCOL.json').exists():atomic(base/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),seeds=[0],panel=dict(group_failure=3,other_failure=2,success=2,intermediate=1),
           fitted_spaces_per_location=2,space_allocation='Rotate success/failure PCA and basis/variance residual, alternating low/high ranks. Refine all retained spaces at selected sites.',
           methods=['mean','contract','ot','quality','local','qda_gradient','remove','project','soft_clip'],
           cap_default=.02,additional_methods=['mean','ot','quality'],additional_strength_cap=[[.25,.005],[1.,.1]],
           all_layers_preserved=True,selection_role='Training-only hierarchical search; later broad response matrices and whole-system CV required.',
           validation_accessed=False,test_accessed=False))
    register(dict(name='fold_and_outcome_hierarchical_probes',path=str(base.relative_to(ROOT)),handler='code/r2_eval_rollouts.py',
                  handler_sha256=sha(ROOT/'code/r2_eval_rollouts.py'),kind='rollouts',priority=30))
    specs={};protocols=set();queue=read(base/'tasks.json');known={t['id'] for t in queue}
    handled={t['id'].rsplit('_',1)[0] for t in queue};skipped=read(base/'producer.json').get('skipped',[])
    handled.update(t['id'] for t in skipped)
    while True:
        paths=[ROOT/'config/FOLD_LOCATION_PROTOCOL.json']+sorted((ROOT/'config/family_locations').glob('*.json'))
        for path in paths:
            if path in protocols or not path.exists():continue
            d=read(path)
            for task in d['tasks']:
                assert task['id'] not in specs;specs[task['id']]=task
            protocols.add(path)
        changed=False
        for ident,task in list(specs.items()):
            if ident in handled:continue
            result_path=ROOT/'analysis/expert_spaces'/(ident+'.json')
            if not result_path.exists():continue
            result=read(result_path);handled.add(ident);changed=True
            if result['status']!='PASS':skipped.append(dict(id=ident,status=result['status']));continue
            meta_name=task['responsibility_meta'];held=task['heldout_fold'];expert=task['expert']
            if meta_name not in memberships:
                meta=read(ROOT/meta_name)
                with np.load(ROOT/meta['path']) as z:memberships[meta_name]=(np.array(z['global_indices']),np.array(z['responsibility']))
            indices,responsibility=memberships[meta_name]
            if (meta_name,expert) not in panels:
                train=explore&((folds!=held) if held>=0 else True)
                if held not in pools:
                    salt=dict(probe_reference=20261018,held=held)
                    pools[held]=(balanced(np.flatnonzero(train&(quality>.9)),rows,512,salt),
                                 balanced(np.flatnonzero(train&(quality>=.7)&(quality<=.9)),rows,256,salt))
                assert np.all(train[indices]);dominant=np.argmax(responsibility,1)==expert
                salt=dict(group=meta_name,expert=expert,probe=20261018)
                own=balanced(indices[dominant],rows,3,salt)
                if len(own)<3:
                    own += [int(indices[j]) for j in np.argsort(-responsibility[:,expert]) if int(indices[j]) not in own][:3-len(own)]
                other=balanced([i for i in indices[~dominant] if int(i) not in own],rows,2,salt)
                high,mid=pools[held];offset=int(digest(salt)[:8],16)
                success=[high[(offset+j)%len(high)] for j in range(2)];intermediate=[mid[offset%len(mid)]]
                panel=own+other+success+intermediate
                assert len(panel)==len(set(panel)) and np.all(train[panel])
                panels[(meta_name,expert)]=(panel,dict(own=own,other=other,success=success,intermediate=intermediate))
            panel,partitions=panels[(meta_name,expert)]
            parity=int(digest(dict(task=ident,allocation=20261018))[:8],16)
            types=[('success_pca' if parity%2==0 else 'failure_pca'),('basis_residual' if parity%4<2 else 'variance_residual')]
            selected=[]
            for j,kind in enumerate(types):
                options=[f for f in result['fits'] if f['config']['kind']==kind]
                if options:selected.append(sorted(options,key=lambda f:f['r'],reverse=bool((parity+j)%2))[0])
            if not selected:selected=[result['fits'][0]]
            arms=[]
            for fit in selected:
                for method in ['mean','contract','ot','quality','local','qda_gradient','remove','project','soft_clip']:
                    settings=[(1.,.02)]
                    if method in ['mean','ot','quality']:settings += [(.25,.005),(1.,.1)]
                    for alpha,cap in settings:
                        arm=dict(block=fit['block'],group=fit['group'],method=method,alpha=alpha,cap=cap,gate='none',fit_path=fit['path'],fit_sha256=fit['sha256'])
                        arms.append(dict(id='probe_'+digest(arm)[:22],**arm))
            point=base/'points'/(ident+'.json')
            if not point.exists():atomic(point,dict(id=ident,task=task,fit_metadata=selected,all_fit_metadata=result['fits'],arms=arms,panel=panel,
                              panel_partitions=partitions,seeds=[0],training_only=True,actual_outcome_cv=False))
            for start in range(0,len(panel),2):
                enqueue(queue,known,dict(id=ident+'_%02d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+2,len(panel))))
        if changed:
            atomic(base/'tasks.json',queue)
            atomic(base/'producer.json',dict(complete=False,tasks=len(queue),handled=len(handled),specs=len(specs),protocols=len(protocols),skipped=skipped,time=stamp()))
        if len(protocols)==13 and len(handled)==len(specs):break
        time.sleep(30)
    atomic(base/'producer.json',dict(complete=True,tasks=len(queue),handled=len(handled),specs=len(specs),protocols=len(protocols),skipped=skipped,time=stamp()))
    print(json.dumps(dict(status='PRODUCED',tasks=len(queue),points=len(handled)-len(skipped))),flush=True)


if __name__=='__main__':main()
