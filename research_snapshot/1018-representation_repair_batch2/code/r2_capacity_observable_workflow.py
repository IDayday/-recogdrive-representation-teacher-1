"""Bounded larger-expert pilot: calibration, engineering and paired diagnosis."""
from r2_common import *


def calibration(task):
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    response=read(ROOT/task['response']);point=read(ROOT/response['point']);model=read(ROOT/point['training_path']);held=model['heldout_fold'];assert held==0
    train=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held for r in rows])
    pop=np.array([np.sum(train&(q<.7)),np.sum(train&(q>.9)),np.sum(train&(q>=.7)&(q<=.9))])
    assert sha(ROOT/response['matrix'])==response['matrix_sha256']
    with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);s=np.array(z['scores']);ids=list(z['arm_ids'])
    assert np.all(train[ii]);classes=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));counts=np.bincount(classes,minlength=3);w=pop[classes]/counts[classes];w/=w.sum();candidates=[]
    for j,arm in enumerate(ids):
        a=s[:,j];b=s[:,0];events=[float(np.sum(w[:,None]*((a[:,:,c]<1).astype(float)-(b[:,:,c]<1).astype(float)))/3) for c in [1,2]]
        events.append(float(np.sum(w[:,None]*((a[:,:,0]==0).astype(float)-(b[:,:,0]==0).astype(float)))/3))
        candidates.append(dict(arm=arm,pdms_gain=float(np.sum(w[:,None]*(a[:,:,0]-b[:,:,0]))/3),net_events=events,safe=all(v<=1e-12 for v in events)))
    eligible=[c for c in candidates if c['safe']] if model['role']=='safety' else candidates
    choice=max(eligible,key=lambda c:(c['pdms_gain'],c['arm']=='baseline'))
    configuration=dict(point['policies'][0],force_Base=True) if choice['arm']=='baseline' else next(p for p in point['policies'] if p['id']==choice['arm'])
    path=ROOT/'expert_capacity_observable/joint_policies'/(point['id']+'.json');assert not path.exists()
    atomic(path,dict(status='TRAINING_SELECTED_NOT_HELDOUT_VERIFIED',time=stamp(),system=model['system'],heldout_fold=0,kind=model['kind'],tier=model['tier'],role=model['role'],nominal_K=3,active_K=3,
        configuration=configuration,candidates=candidates,chosen_metrics=choice,source_response=task['response'],validation_fitted=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)))


def engineering(task):
    import numpy as np
    stage=ROOT/task['stage'];receipt=read(stage/'receipts'/task['receipt']);result=read(ROOT/receipt['result']['path']);point=read(ROOT/result['task']['point']);groups={}
    for r in result['records']:groups.setdefault((r['token'],r['seed_index']),{})[r['arm']]=r
    assert len(groups)==6
    for g in groups.values():
        baseline=g['baseline']
        for config in point['policies']:
            r=g[config['id']];assert np.isfinite(r['trajectory']).all() and r['seed']==seed(r['token'],r['seed_index'])
            if config.get('force_Base'):assert r['trajectory']==baseline['trajectory'] and r['score']==baseline['score']
    for path in task['models']:
        m=read(ROOT/path);assert m['base_frozen'] and m['experts_frozen'] and any(r['gradient_norm']>0 for r in m['trace'])
        assert all(p['training_task']['rank'] in [128,256] for p in m['parts'])
    nonzero=[p['id'] for p in point['policies'] if p['model']['kind']=='soft_joint' and not p.get('force_Base') and any(g[p['id']]['trajectory']!=g['baseline']['trajectory'] for g in groups.values())]
    assert len(nonzero)==2
    path=ROOT/'provenance/CAPACITY_OBSERVABLE_JOINT_ENGINEERING_PASS.json';atomic(path,dict(status='PASS',time=stamp(),actual_result=receipt['result'],models=task['models'],hard_soft_and_ranks=[128,256],
        actual_zero_exact=True,actual_nonzero_soft_by_both_ranks=nonzero,finite_gradients=True,real_scores=True,validation_accessed=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)))


def analysis(task):
    import numpy as np
    from r2_bank_potential import metrics
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);columns=[];results=[];by_key={};reference=None;ii=None
    protocol=read(ROOT/task['protocol']);variants={v['id']:v for v in protocol['variants']}
    for path in task['responses']:
        response=read(ROOT/path);assert sha(ROOT/response['matrix'])==response['matrix_sha256'];point=read(ROOT/response['point'])
        with np.load(ROOT/response['matrix']) as z:indices=np.array(z['global_indices']);s=np.array(z['scores']);ids=list(z['arm_ids']);noise=np.array(z['seeds'])
        assert list(noise)==[0,1,2]
        if ii is None:
            ii=indices;reference=s[:,0];mask=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==0 for r in rows]);classes=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));pop=np.array([np.sum(mask&(q<.7)),np.sum(mask&(q>.9)),np.sum(mask&(q>=.7)&(q<=.9))]);w=pop[classes]/np.bincount(classes,minlength=3)[classes];w/=w.sum()
        else:assert np.array_equal(ii,indices) and np.array_equal(reference,s[:,0])
        for ident,meta in point['policy_metadata'].items():
            after=s[:,ids.index(ident)];variant=variants[meta['variant']];gain=(after[:,:,0]-reference[:,:,0])*100;events=[]
            for n in range(3):
                events.append([float(np.sum(w*((after[:,n,c]<1).astype(float)-(reference[:,n,c]<1).astype(float)))) for c in [1,2]]+[float(np.sum(w*((after[:,n,0]==0).astype(float)-(reference[:,n,0]==0).astype(float))))])
            r=dict(id=ident,**meta,rank=variant['rank'],budget_factor=variant['budget_factor'],K=3,standardized_gain_by_noise=np.sum(w[:,None]*gain,axis=0).tolist(),
                standardized_mean_gain=float(np.sum(w[:,None]*gain)/3),standardized_net_safety_events_by_noise=events,approx_safety_all_noise=bool(np.all(np.asarray(events)<=1e-12)),
                sampled_case_metrics_by_noise=[metrics(after[:,n],reference[:,n],w) for n in range(3)])
            results.append(r);by_key[(meta['variant'],meta['method'],meta['role'],meta['tier'])]=gain.mean(1)
    assert len(results)==110
    comparisons=[]
    for r in results:
        values=by_key[(r['variant'],r['method'],r['role'],r['tier'])]
        comparisons.append(dict(policy=r['id'],comparison='against_Base'));columns.append(values)
        if r['variant']!='capacity_r32_b1':
            ref=by_key[('capacity_r32_b1',r['method'],r['role'],r['tier'])]
            comparisons.append(dict(policy=r['id'],comparison='against_fresh_rank32_budget1_same_method'));columns.append(values-ref)
    sessions=sorted({rows[int(i)]['session'] for i in ii});membership=np.array([sessions.index(rows[int(i)]['session']) for i in ii]);x=np.stack(columns,1);cluster=np.zeros((len(sessions),len(columns)));mass=np.zeros(len(sessions));np.add.at(cluster,membership,x*w[:,None]);np.add.at(mass,membership,w);observed=cluster.sum(0)
    rng=np.random.default_rng(2026101893);boot=[];extreme=np.zeros(len(columns),int)
    for start in range(0,10000,250):
        pick=rng.integers(len(sessions),size=(250,len(sessions)));boot.append(cluster[pick].sum(1)/mass[pick].sum(1)[:,None])
    boot=np.concatenate(boot)
    for start in range(0,19999,500):
        sign=rng.integers(2,size=(min(500,19999-start),len(sessions)))*2-1;extreme+=np.sum(np.abs(sign@cluster)>=np.abs(observed)[None]-1e-12,axis=0)
    p=(extreme+1)/20000;adjusted=np.zeros(len(p));previous=0.
    for rank,index in enumerate(np.argsort(p)):previous=max(previous,min(1.,(len(p)-rank)*p[index]));adjusted[index]=previous
    for j,c in enumerate(comparisons):c.update(mean_difference=float(observed[j]),fixed_sampling_weight_session_bootstrap95=np.quantile(boot[:,j],[.025,.975]).tolist(),approximate_session_signflip_p=float(p[j]),Holm_p=float(adjusted[j]))
    path=ROOT/'analysis/expert_capacity_observable/SUMMARY.json';assert not path.exists();atomic(path,dict(status='COMPLETE_BOUNDED_OBSERVABLE_CAPACITY_PILOT',time=stamp(),cases=len(ii),sessions=len(sessions),protocol=task['protocol'],protocol_sha256=sha(ROOT/task['protocol']),responses=task['responses'],results=results,paired_comparisons=comparisons,
        multiplicity=dict(hypotheses=len(p),all_policies_andnegative_results=True,bootstrap=10000,signflip=19999),
        scope='Single exploration-fold0 development pilot; same1135 cases, paired seeds and ownK3. All policies use observable information and real fresh rollouts; fixed sampling-weight statistics approximate. Not fullfivefold/threefit/natural validation.',validation_accessed=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)))


def run(task):
    return {'calibrate':calibration,'engineering':engineering,'analyze':analysis}[task['mode']](task)
