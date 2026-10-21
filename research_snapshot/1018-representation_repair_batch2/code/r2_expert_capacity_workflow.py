"""Matched capacity pilot: engineering, training-only choices and held diagnosis.

Oracle results stay separate from observable policy cross-validation.
"""
from r2_common import *


def engineering(engine,task,pool):
    import numpy as np
    import r2_learned_expert_v4_nativecache as reference
    import r2_expert_capacity_training as controlled
    import r2_learned_eval as raw
    import r2_expert_capacity_eval_cached as cached
    protocol=read(ROOT/task['protocol']);assert sha(ROOT/task['protocol'])==task['protocol_sha256'];original=read(ROOT/'runs/behavior_experts_v1/tasks.json');models=[];pairs=[]
    for block in protocol['sites']:
        parent=next(t for t in original if t['system']==protocol['system'] and t['heldout_fold']==0 and t['expert']==0 and t['block']==block)
        for rank in protocol['ranks']:
            spec=dict(parent,rank=rank,steps=8,checkpoints=[8]);spec['id']='capacity_engineering_'+block+'_r'+str(rank)
            result=controlled.run(engine,spec,pool);model=read(ROOT/result['path']);assert model['base_weights_frozen'];models.append(model)
            if rank==32:
                ref=dict(spec,id='capacity_reference_'+block);r=reference.run(engine,ref,pool);d=read(ROOT/r['path'])
                with np.load(ROOT/d['checkpoints'][0]['path']) as a,np.load(ROOT/model['checkpoints'][0]['path']) as b:assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
                assert d['records']==model['records'];pairs.append(dict(block=block,reference=r['path'],controlled=result['path'],weights_and_trace_bitwise_equal=True))
    rows=read(read(ROOT/'manifests/data_source.json')['rows']);lookup={r['token']:i for i,r in enumerate(rows)};panel=[lookup[a['token']] for a in read(ROOT/'manifests/anchors.json')[:2]];arms=[]
    for m in models:
        for strength in [.5,1.]:
            s=dict(training_task=m['task'],checkpoint=m['checkpoints'][0],strength=strength);arms.append(dict(id='capacity_smoke_arm_'+digest(s)[:20],kind='learned',slot=0,**s))
    stage=ROOT/'runs/expert_capacity_engineering_v1';outputs=[]
    for name,module in [('raw',raw),('cached',cached)]:
        point=stage/'points'/(name+'.json');atomic(point,dict(id=name,panel=panel,seeds=[0,1,2],arms=arms,training_only=True));t=dict(id='capacity_eval_'+name,stage=str(stage.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=0,end=len(panel));result=module.run(engine,t,pool);outputs.append(result)
    a=read(ROOT/outputs[0]['path']);b=read(ROOT/outputs[1]['path']);assert a['records']==b['records'];assert len(a['records'])==78
    proof=ROOT/'provenance/EXPERT_CAPACITY_CONTROL_ENGINEERING_PASS.json';atomic(proof,dict(status='PASS_EXACT_MATCHED_TRAINING_AND_RAW_CACHED_EVALUATION',time=stamp(),protocol=task['protocol'],protocol_sha256=task['protocol_sha256'],rank32_original_training_vs_namespace_copy=pairs,all_ranks_sites_nonzero_trained=True,eval_reference=outputs[0],eval_cached=outputs[1],actual_complete_records_per_runtime=78,actual_seed_trajectory_score_and_relative_edit_exact=True,raw_and_cached_eval_seconds=[a['seconds'],b['seconds']],single_short_timing_not_sustained_speedup=True,not_deployment_or_science_gain=True))
    return dict(path=str(proof.relative_to(ROOT)))


def select_banks(task):
    import numpy as np
    from collections import defaultdict
    protocol=read(ROOT/task['protocol']);meta=read(ROOT/task['responsibility_meta']);assert meta['heldout_fold']==0
    with np.load(ROOT/meta['path']) as z:indices=np.array(z['global_indices']);membership=np.array(z['responsibility'])
    positions={int(i):j for j,i in enumerate(indices)};options=defaultdict(list);sources=[]
    for path in task['responses']:
        response=read(ROOT/path);assert sha(ROOT/response['matrix'])==response['matrix_sha256'];point=read(ROOT/response['point']);model=point['task'];assert model['heldout_fold']==0 and model['system']==protocol['system']
        with np.load(ROOT/response['matrix']) as z:s=np.array(z['scores']);ii=np.array(z['global_indices']);ids=list(z['arm_ids'])
        arms={a['id']:a for a in point['arms']};base=s[:,0];slot=model['expert'];w=np.array([membership[positions[int(i)],slot] if int(i) in positions else 0. for i in ii]);assert w.sum()>0
        for j,ident in enumerate(ids[1:],1):
            arm=arms[ident];factor=arm['budget_factor'];after=s[:,j];gain=float(np.sum(w[:,None]*(after[:,:,0]-base[:,:,0]))/(w.sum()*3));events=[int(np.sum(after[:,:,c]<1)-np.sum(base[:,:,c]<1)) for c in [1,2]]+[int(np.sum(after[:,:,0]==0)-np.sum(base[:,:,0]==0))]
            options[(model['rank'],factor,slot)].append(dict(part=arm,own_weighted_gain=gain,net_events=events,safe_panel=all(v<=0 for v in events),source=path))
        sources.append(dict(path=path,sha256=sha(ROOT/path)))
    banks=[];parts={}
    for rank in protocol['ranks']:
        for factor in protocol['budget_factors']:
            policies={};selection=[]
            for role in ['PDMS','safety']:
                selected=[]
                for slot in protocol['experts']:
                    values=options[(rank,factor,slot)];assert len(values)==6
                    eligible=[v for v in values if v['safe_panel']]
                    best=max(values,key=lambda v:v['own_weighted_gain']) if role=='PDMS' else max(eligible,key=lambda v:v['own_weighted_gain']) if eligible else min(values,key=lambda v:(sum(max(e,0) for e in v['net_events']),-v['own_weighted_gain']))
                    arm=best['part'];selected.append(arm['id']);parts[arm['id']]=arm;selection.append(dict(role=role,expert=slot,chosen=best,all_options=values))
                policies[role]=selected
            ident=f'capacity_r{rank}_b{factor}';path=ROOT/'expert_capacity_controls/banks'/(ident+'.json');atomic(path,dict(status='TRAINING_ONLY_FROZEN_OWN_K_CANDIDATES',time=stamp(),id=ident,rank=rank,budget_factor=factor,K=3,heldout_fold=0,policies=policies,selection=selection,protocol=task['protocol'],sources=sources,diagnostic_only=True));banks.append(dict(id=ident,path=str(path.relative_to(ROOT)),sha256=sha(path),policies=policies,rank=rank,budget_factor=factor))
    path=ROOT/'expert_capacity_controls/banks/COMPLETE.json';atomic(path,dict(status='COMPLETE',time=stamp(),banks=banks,parts=list(parts.values()),source_quick_responses=sources,all_variants_retained=True,no_held_score_selection=True));return dict(path=str(path.relative_to(ROOT)))


def analyze(task):
    import numpy as np
    from r2_bank_potential import metrics
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);response=read(ROOT/task['response']);assert sha(ROOT/response['matrix'])==response['matrix_sha256'];point=read(ROOT/response['point'])
    with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);s=np.array(z['scores']);noise=np.array(z['seeds'])
    assert list(noise)==[0,1,2] and all(rows[int(i)]['subset']=='exploration' and int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5==0 for i in ii)
    mask=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==0 for r in rows]);classes=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));population=np.array([np.sum(mask&(q<.7)),np.sum(mask&(q>.9)),np.sum(mask&(q>=.7)&(q<=.9))]);counts=np.bincount(classes,minlength=3);w=population[classes]/counts[classes];w/=w.sum();base=s[:,0];results=[];values={}
    for bank in point['banks']:
        assert sha(ROOT/bank['path'])==bank['sha256']
        for role,parts in bank['policies'].items():
            allowed=[ids.index(v) for v in ['baseline']+parts];actual=s[:,allowed];pick=actual[:,:,:,0].argmax(1);after=np.stack([actual[np.arange(len(ii)),pick[:,n],n] for n in range(3)],axis=1);key=bank['id']+'_'+role;values[key]=after;forced={ident:[metrics(s[:,ids.index(ident),n],base[:,n],w) for n in range(3)] for ident in parts}
            results.append(dict(id=key,rank=bank['rank'],budget_factor=bank['budget_factor'],role=role,K=3,identity_additional=True,own_candidate_ids=parts,oracle_by_noise=[metrics(after[:,n],base[:,n],w) for n in range(3)],unconditional_each_expert=forced,privileged=True))
    sessions=sorted({rows[int(i)]['session'] for i in ii});membership=np.array([sessions.index(rows[int(i)]['session']) for i in ii]);comparisons=[];columns=[]
    for result in results:
        if result['rank']==32 and result['budget_factor']==1:continue
        ref='capacity_r32_b1_'+result['role'];delta=(values[result['id']][:,:,0]-values[ref][:,:,0])*100
        for label,v in [('S0',delta[:,0]),('S1S2_fixed_policy',delta[:,1:].mean(1))]:columns.append(v);comparisons.append(dict(variant=result['id'],reference=ref,endpoint=label))
    matrix=np.stack(columns,axis=1);cluster=np.zeros((len(sessions),matrix.shape[1]));mass=np.zeros(len(sessions));np.add.at(cluster,membership,matrix*w[:,None]);np.add.at(mass,membership,w);observed=cluster.sum(0);rng=np.random.default_rng(2026101887);bootstrap=[];extreme=np.zeros(len(comparisons),int)
    for start in range(0,10000,250):
        pick=rng.integers(len(sessions),size=(250,len(sessions)));bootstrap.append(cluster[pick].sum(1)/mass[pick].sum(1)[:,None])
    bootstrap=np.concatenate(bootstrap)
    for start in range(0,19999,500):
        n=min(500,19999-start);sign=rng.integers(2,size=(n,len(sessions)))*2-1;extreme+=np.sum(np.abs(sign@cluster)>=np.abs(observed)[None]-1e-12,axis=0)
    p=(extreme+1)/20000;adjusted=np.zeros(len(p));previous=0.
    for rank,index in enumerate(np.argsort(p)):previous=max(previous,min(1.,(len(p)-rank)*p[index]));adjusted[index]=previous
    for j,c in enumerate(comparisons):c.update(mean_difference=float(observed[j]),fixed_sampling_weight_session_bootstrap95=np.quantile(bootstrap[:,j],[.025,.975]).tolist(),approximate_session_signflip_p=float(p[j]),Holm_p=float(adjusted[j]))
    path=ROOT/'analysis/expert_capacity_control/SUMMARY.json';atomic(path,dict(status='COMPLETE_BOUNDED_CAPACITY_CONVERGENCE_DIAGNOSTIC',time=stamp(),task=task,response=task['response'],response_sha256=sha(ROOT/task['response']),cases=len(ii),sessions=len(sessions),results=results,paired_comparisons=comparisons,multiplicity=dict(hypotheses=len(p),all32_comparisons_including_negative=True,bootstrap=10000,signflip=19999),scope='Single exploration-fold0 privileged own-K candidate diagnosis; same grouping, samples, targets, optimizer andnorm cap. Fixed case sampling-weight session bootstrap is approximate; no natural-population deployment gain.',all9_variants_andboth_roles_reported=True,no_cross_variant_union_Oracle=True,validation_accessed=False,test_accessed=False));return dict(path=str(path.relative_to(ROOT)))


def run(*args):
    if len(args)==3:return engineering(*args)
    task=args[0]
    return select_banks(task) if task['mode']=='select' else analyze(task)
