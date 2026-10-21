"""Reproducible whole-system held-session summaries, never test-set selection."""
from r2_common import *
from collections import defaultdict
from functools import lru_cache


@lru_cache(maxsize=1)
def population():
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    explore=np.asarray([r['subset']=='exploration' for r in rows]);fold=np.asarray([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    classes=np.where(quality<.7,0,np.where(quality>.9,1,2))
    counts=np.asarray([[np.sum(explore&(fold==f)&(classes==c)) for c in range(3)] for f in range(5)])
    return rows,classes,fold,explore,counts


def run(task):
    import numpy as np
    import csv
    rows,quality_class,fold,explore,pop=population();groups=defaultdict(dict);sources=[];point_rows=[]
    for path in task['responses']:
        response=read(ROOT/path);assert response['source_mode']=='heldout'
        point=read(ROOT/response['point']);held=point['heldout_fold'];assert held in range(5)
        with np.load(ROOT/response['matrix']) as z:
            ii=np.array(z['global_indices']);arms=list(z['arm_ids']);seeds=np.array(z['seeds']);s=np.array(z['scores'])
        assert np.all(explore[ii]&(fold[ii]==held)) and len(set(ii.tolist()))==len(ii)
        assert list(seeds)==[0,1,2] and arms[0]=='baseline'
        stage=Path(response['task']['stage']).name;method=stage.replace('_cv_v1','').replace('_policy','')
        if point.get('kind'):method+='_'+point['kind']
        source_info=dict(path=path,matrix_sha256=response['matrix_sha256'],point=response['point'],heldout_fold=held,cases=len(ii),system=point['system'])
        sources.append(source_info)
        for a,arm in enumerate(arms[1:],1):
            key=(method,point['system'],str(arm));assert held not in groups[key],('Duplicate held policy',key,held)
            base=s[:,0];after=s[:,a];cls=quality_class[ii];sample=np.bincount(cls,minlength=3);assert np.all(sample>0)
            weights=np.asarray([pop[held,c]/sample[c] for c in cls]);weights/=weights.sum()
            delta=after[:,:,0]-base[:,:,0]
            rates=np.stack([(after[:,:,1]<1).astype(float)-(base[:,:,1]<1).astype(float),
                (after[:,:,2]<1).astype(float)-(base[:,:,2]<1).astype(float),
                (after[:,:,0]==0).astype(float)-(base[:,:,0]==0).astype(float),
                (after[:,:,3]<1).astype(float)-(base[:,:,3]<1).astype(float),
                (after[:,:,0]<.7).astype(float)-(base[:,:,0]<.7).astype(float)],axis=-1)
            per_seed=(weights[:,None]*delta).sum(0)*100
            standardized_rates=(weights[:,None,None]*rates).sum(0)
            detail=dict(method=method,system=point['system'],policy=str(arm),heldout_fold=held,cases=len(ii),
                class_counts=sample.tolist(),standardized_pdms_gain_by_noise=per_seed.tolist(),
                standardized_net_event_rates_by_noise=standardized_rates.tolist(),
                sampled_net_event_counts_by_noise=rates.sum(0).astype(int).tolist(),
                repaired70_by_noise=np.sum((base[:,:,0]<.7)&(after[:,:,0]>=.7),axis=0).tolist(),
                repaired90_by_noise=np.sum((base[:,:,0]<.7)&(after[:,:,0]>.9),axis=0).tolist(),
                original_high_lost_by_noise=np.sum((base[:,:,0]>.9)&(after[:,:,0]<=.9),axis=0).tolist(),
                damaged_by_noise=np.sum(delta< -1e-8,axis=0).tolist())
            point_rows.append(detail)
            session_names=sorted({rows[int(i)]['session'] for i in ii});lookup={v:j for j,v in enumerate(session_names)}
            sessions=np.asarray([lookup[rows[int(i)]['session']] for i in ii]);ss=np.zeros((len(session_names),3,4),dtype=np.float64)
            for c in range(3):
                mask=cls==c;np.add.at(ss[:,c,0],sessions[mask],1.)
                for n in range(3):np.add.at(ss[:,c,n+1],sessions[mask],delta[mask,n])
            groups[key][held]=dict(detail=detail,session_stats=ss,session_names=session_names)
    results=[];rng=np.random.default_rng(2026101809)
    for key,folds in sorted(groups.items()):
        complete=set(folds)==set(range(5));available=sorted(folds);total=pop[available].sum();mean_by_noise=np.zeros(3);rates=np.zeros((3,5));bootstrap=np.zeros(task.get('bootstrap_samples',1000));permutation=np.zeros_like(bootstrap);observed=0.
        for held,d in sorted(folds.items()):
            mass=pop[held].sum()/total;mean_by_noise+=mass*np.asarray(d['detail']['standardized_pdms_gain_by_noise']);rates+=mass*np.asarray(d['detail']['standardized_net_event_rates_by_noise'])
            ss=d['session_stats'];fractions=pop[held]/pop[held].sum();count=ss[:,:,0].sum(0)
            cluster_delta=(ss[:,:,1:].mean(2)/count[None,:]*fractions[None,:]).sum(1)*mass*100
            observed+=cluster_delta.sum()
            # Sessions remain the resampling unit; noise draws are paired repeated
            # outcomes, never counted as independent scenes.
            for start in range(0,len(bootstrap),100):
                n=min(100,len(bootstrap)-start);pick=rng.integers(len(ss),size=(n,len(ss)));sampled=ss[pick].sum(1)
                means=np.divide(sampled[:,:,1:].mean(2),sampled[:,:,0],out=np.zeros((n,3)),where=sampled[:,:,0]>0)
                bootstrap[start:start+n]+=means@fractions*mass*100
                signs=rng.integers(2,size=(n,len(ss)))*2-1;permutation[start:start+n]+=signs@cluster_delta
        ci=np.quantile(bootstrap,[.025,.975]);pvalue=(1+np.sum(np.abs(permutation)>=abs(observed)))/(len(permutation)+1)
        method,system,policy=key
        item=dict(method=method,system=system,policy=policy,folds=available,complete_five_folds=complete,
            sessions=sum(len(d['session_names']) for d in folds.values()),sampled_cases=sum(d['detail']['cases'] for d in folds.values()),
            standardized_pdms_gain=float(mean_by_noise.mean()),standardized_pdms_gain_by_noise=mean_by_noise.tolist(),
            session_bootstrap_95=ci.tolist(),cluster_signflip_two_sided_p=float(pvalue),
            standardized_net_event_rates_by_noise=rates.tolist(),
            approximate_safety_all_noise=bool(np.all(rates[:,:3]<=1e-12)),
            interpretation='Class-standardized session-balanced sampled panel. Not an unbiased full-natural-population estimate; independent full validation required.')
        results.append(item)
    # One exploratory correction family includes every reported complete recipe,
    # including negative/Base-like systems; do not correct only winners.
    complete=[d for d in results if d['complete_five_folds']];ordered=sorted(complete,key=lambda d:d['cluster_signflip_two_sided_p']);previous=0.
    for j,d in enumerate(ordered):
        previous=max(previous,min(1.,(len(ordered)-j)*d['cluster_signflip_two_sided_p']));d['holm_p']=previous
    folder=ROOT/'analysis/extended_cv_reviews'/task['id'];folder.mkdir(parents=True,exist_ok=False)
    atomic(folder/'SUMMARY.json',dict(status='EXPLORATORY_CROSS_VALIDATION_REVIEW',time=stamp(),sources=sources,recipes=results,fold_points=point_rows,
        full_cv_recipes=len(complete),partial_recipes=len(results)-len(complete),bootstrap_samples=len(bootstrap) if results else 0,
        event_columns=['collision','offroad','zero','TTC','failure'],quality_class_definition=['S0_PDMS<70','S0_PDMS>90','70<=S0_PDMS<=90'],
        cv_used_for_development=True,multiplicity='Holm across all complete recipes in this snapshot; session sign-flip p is an exploratory exchangeability approximation, not independent confirmation.',
        incomplete_folds_never_ranked_as_full_cv=True,validation_accessed=False,test_accessed=False))
    with (folder/'recipes.csv').open('w',newline='') as stream:
        fields=['method','system','policy','complete_five_folds','folds','sampled_cases','sessions','standardized_pdms_gain','standardized_pdms_gain_by_noise','session_bootstrap_95','approximate_safety_all_noise','holm_p'];writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(results)
    atomic(ROOT/'analysis/extended_cv_reviews/LATEST.json',dict(time=stamp(),path=str((folder/'SUMMARY.json').relative_to(ROOT)),sha256=sha(folder/'SUMMARY.json'),full_cv_recipes=len(complete),partial_recipes=len(results)-len(complete)))
    return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),full_cv_recipes=len(complete),partial_recipes=len(results)-len(complete))
