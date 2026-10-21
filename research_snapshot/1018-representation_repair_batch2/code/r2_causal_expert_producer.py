"""Fold-specific outcome-derived regression experts, true feedback, then routing.

Every subgroup owns its output basis. Parameters are proposed by an explicit
small grid and selected from actually generated paired outcomes, not MSE/energy.
"""
from r2_common import *
from r2_resume_support import append_once,register_once,enqueue
from r2_coarse_producer import balanced
from collections import defaultdict


def main():
    setup('causal_expert_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')};model_tasks=read(ROOT/'runs/behavior_experts_v1/tasks.json')
    groups={}
    for t in model_tasks:groups[(t['responsibility_meta'],t['expert'])]=t
    fit_tasks=[]
    for (meta,expert),parent in groups.items():
        for site in ['interface_pre','interface_post']:
            dimension=cells[site+'__valid_mean']['shape'][1]
            spec=dict(block=site,cap=.1,responsibility_meta=meta,expert=expert,heldout_fold=parent['heldout_fold'],fit_seed=parent['fit_seed'],
                input_ranks=[128,dimension],output_ranks=[32,128],ridge=[.01,.1],retention_weight=2.,safety_targets=False)
            fit_tasks.append(dict(id='outcome_causal_fit_'+digest(spec)[:24],handler='code/r2_delta_regression_v3.py',handler_sha256=sha(ROOT/'code/r2_delta_regression_v3.py'),**spec))
    protocol=ROOT/'config/CAUSAL_EXPERT_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),fit_tasks=fit_tasks,K=list(range(2,9)),families=['representation','response','correction'],folds=[-1,0,1,2,3,4],
        input_spaces='PCA128 and genuine full input',own_output_ranks=[32,128],ridge=[.01,.1],cap=.1,strengths=[.5,1.],noise=[0,1,2],
        proposal_panel=dict(own_failure=6,other_failure=2,high=2,intermediate=2),
        motivation='Global training calibration suggested full input deserves evaluation. All settings independently refitted/selected within each outer training fold; final validation untouched.',
        MSE_or_energy_not_selection_criteria=True,validation_fitted=False,test_accessed=False))
    append_once('cpu',fit_tasks)
    quick=ROOT/'runs/causal_expert_quick_v1';library=[ROOT/'runs/causal_library_S0_v1',ROOT/'runs/causal_library_noise_v1'];stages=[quick]+library;queues={};known={}
    for base,priority in zip(stages,[23.85,23.15,23.65]):
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        queues[base]=read(base/'tasks.json');known[base]={t['id'] for t in queues[base]}
        register_once(dict(name=base.name,path=str(base.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=priority))
    grouped=defaultdict(list)
    for t in fit_tasks:
        meta=read(ROOT/t['responsibility_meta']);grouped[(meta['heldout_fold'],meta['id'])].append(t)
    published=set();selected=set();banked=set();panels={};own_panels={};membership={}
    while True:
        changes=set();bank_tasks=[]
        for task in fit_tasks:
            if task['id'] in published:continue
            path=ROOT/'analysis/delta_experts'/(task['id']+'.json')
            if not path.exists():continue
            result=read(path);meta_path=task['responsibility_meta'];held=task['heldout_fold'];key=(meta_path,task['expert'])
            if key not in own_panels:
                if meta_path not in membership:
                    meta=read(ROOT/meta_path)
                    with np.load(ROOT/meta['path']) as z:membership[meta_path]=(np.array(z['global_indices']),np.array(z['responsibility']))
                ii,q=membership[meta_path];own=q.argmax(1)==task['expert'];salt=dict(causal_expert_quick=20261018,group=meta_path,expert=task['expert'])
                f=balanced(ii[own],rows,6,salt)
                if len(f)<6:f += [int(ii[j]) for j in np.argsort(-q[:,task['expert']]) if int(ii[j]) not in f][:6-len(f)]
                other=balanced([int(i) for i in ii[~own] if int(i) not in f],rows,2,salt)
                train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
                h=balanced(np.flatnonzero(train&(quality>.9)),rows,2,salt);m=balanced(np.flatnonzero(train&(quality>=.7)&(quality<=.9)),rows,2,salt)
                own_panels[key]=(f+other+h+m,dict(own=f,other=other,high=h,intermediate=m))
            panel,parts=own_panels[key];arms=[]
            for fit in result.get('fits',[]):
                for strength in [.5,1.]:
                    spec=dict(kind='delta',fit=fit,strength=strength,slot=task['expert']);arms.append(dict(id='causal_arm_'+digest(spec)[:24],**spec))
            if not arms:
                published.add(task['id']);continue
            point=quick/'points'/(task['id']+'.json')
            if not point.exists():atomic(point,dict(id=task['id'],task=task,arms=arms,panel=panel,panel_partitions=parts,seeds=[0,1,2],training_only=True))
            for start in range(0,len(panel),4):enqueue(queues[quick],known[quick],dict(id=task['id']+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(quick.relative_to(ROOT))))
            published.add(task['id']);changes.add(quick)
        for (held,system),tasks in grouped.items():
            ident='causal_library_'+digest(dict(held=held,system=system))[:24]
            if ident not in selected:
                fit_results=[ROOT/'analysis/delta_experts'/(t['id']+'.json') for t in tasks]
                if not all(p.exists() for p in fit_results):continue
                usable=[t for t,p in zip(tasks,fit_results) if read(p).get('fits')]
                response_paths=[ROOT/'analysis/responses/causal_expert_quick_v1'/(t['id']+'.json') for t in usable]
                # Different experts have deliberately different own-case panels.
                # Select each slot from its two site matrices, then combine K.
                by_expert=defaultdict(list)
                for t,p in zip(usable,response_paths):by_expert[t['expert']].append((t,p))
                if not usable:
                    atomic(ROOT/'analysis/causal_experts/ineligible'/(ident+'.json'),dict(time=stamp(),system=system,heldout_fold=held,reason='No eligible causal output rank in any slot',nominal_K=read(ROOT/tasks[0]['responsibility_meta'])['K']))
                    selected.add(ident);continue
                if all(p.exists() for p in response_paths):
                    spec=dict(system=system.replace('_K','_causal_K',1),responsibility_meta=tasks[0]['responsibility_meta'],responses=[str(p.relative_to(ROOT)) for p in response_paths],allow_different_slot_panels=True)
                    bank_tasks.append(dict(id=ident,handler='code/r2_causal_bank_v2.py',handler_sha256=sha(ROOT/'code/r2_causal_bank_v2.py'),**spec));selected.add(ident)
            selection_path=ROOT/'analysis/causal_library_selection'/(ident+'.json')
            if ident in banked or not selection_path.exists():continue
            selection=read(selection_path)
            if held not in panels:
                # Exactly the original full feedback panel, so later heterogeneous
                # expert selection can compare methods without mismatched rows.
                source_point=None
                for p in (ROOT/'runs/expert_library_S0_v1/points').glob('*.json'):
                    d=read(p)
                    if d['heldout_fold']==held:source_point=d;break
                if source_point is None:continue
                noise_point=read(ROOT/'runs/expert_library_noise_v1/points'/(source_point['id']+'.json'))
                panels[held]=[(source_point['panel'],source_point['panel_partitions']),(noise_point['panel'],noise_point['panel_partitions'])]
            for n,base,seeds in [(0,library[0],[0]),(1,library[1],[1,2])]:
                panel,parts=panels[held][n];point=base/'points'/(ident+'.json')
                if not point.exists():atomic(point,dict(id=ident,system=selection['system'],K=selection['K'],heldout_fold=held,arms=selection['arms'],policies=selection['policies'],selection=str(selection_path.relative_to(ROOT)),panel=panel,panel_partitions=parts,seeds=seeds,training_only=True))
                for start in range(0,len(panel),8):enqueue(queues[base],known[base],dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+8,len(panel)),stage=str(base.relative_to(ROOT))))
                changes.add(base)
            banked.add(ident)
        if bank_tasks:append_once('cpu',bank_tasks)
        for base in changes:atomic(base/'tasks.json',queues[base]);atomic(base/'producer.json',dict(complete=False,tasks=len(queues[base]),time=stamp(),fit_proposals=len(published),libraries=len(banked)))
        atomic(ROOT/'analysis/causal_experts/PRODUCER.json',dict(time=stamp(),fit_tasks=len(fit_tasks),quick_points=len(published),selections=len(selected),libraries=len(banked)))
        time.sleep(60)


if __name__=='__main__':main()
