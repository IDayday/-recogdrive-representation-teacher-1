"""Training-only per-expert, per-location proposals; causal selection uses later rollouts."""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def inputs():
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    exploration=np.array([r['subset']=='exploration' for r in rows])
    failure=np.flatnonzero(exploration&(q<.7))
    systems=read(ROOT/'analysis/initial_groups/all/COMPLETE.json')['initialization_systems']
    weights=[];experts=[]
    for system in systems:
        with np.load(ROOT/system['path']) as data:
            assert np.array_equal(data['global_indices'],failure)
            membership=np.array(data['responsibility'],dtype=np.float64)
        for expert in range(system['K']):
            weights.append(membership[:,expert])
            experts.append(dict(system=system['id'],K=system['K'],fit_seed=system['fit_seed'],expert=expert,
                                responsibility_path=system['path'],responsibility_sha256=system['sha256']))
    high=np.flatnonzero(exploration&(q>.9))
    high_order=np.array(sorted(high,key=lambda i:digest({'token':rows[i]['token'],'proposal_high':20261018})))
    return rows,q,exploration,failure,np.stack(weights,1),experts,high_order


def weighted_auc(high,failed,weights):
    import numpy as np
    ordered=np.sort(high)
    less=np.searchsorted(ordered,failed,side='left')
    equal=np.searchsorted(ordered,failed,side='right')-less
    return float(np.dot(weights,less+.5*equal)/(len(high)*weights.sum()))


def run(task):
    import numpy as np
    rows,q,exploration,failure,weights,experts,high_order=inputs()
    cell=task['cell'];x=np.load(cell['absolute_path'],mmap_mode='r')
    valid=np.isfinite(x[:,0]);fi=failure[valid[failure]]
    if len(fi)<24:
        result=dict(status='INELIGIBLE',cell=cell['cell'],reason='fewer than24 valid failures')
        atomic(ROOT/'analysis/group_proposals'/(cell['cell']+'.json'),result);return result
    all_high=np.flatnonzero(exploration&(q>.9)&valid)
    if len(all_high)<24:
        result=dict(status='INELIGIBLE',cell=cell['cell'],reason='fewer than24 valid highs')
        atomic(ROOT/'analysis/group_proposals'/(cell['cell']+'.json'),result);return result
    moment_root=OLD/('vlm_semantic_v2' if cell['group'].endswith('_v2') else 'vlm_repair_v1')/'moments'
    moment=moment_root/(cell['cell']+'.npz')
    if moment.exists():
        with np.load(moment) as m:
            assert int(m['ns'])==len(all_high)
            mean=np.array(m['ss'],dtype=np.float64)/int(m['ns'])
            variance=np.maximum(np.diag(m['gs'])/int(m['ns'])-mean**2,1e-12)
    else:
        a=np.asarray(x[all_high],dtype=np.float64);mean=a.mean(0);variance=np.maximum(a.var(0),1e-12)
    ff=np.asarray(x[fi],dtype=np.float64);w=weights[valid[failure]]
    count=w.sum(0);means=(ff.T@w)/np.maximum(count,1e-12)
    variances=(np.square(ff).T@w)/np.maximum(count,1e-12)-np.square(means)
    directions=(means-mean[:,None])/np.maximum((variance[:,None]+variances)*.5,1e-8)
    # In-sample descriptors only. Cross-fitted interventions and whole-system
    # outcomes decide retention; no p-values or held-out quality claims here.
    high=high_order[valid[high_order]][:2048]
    high_scores=(np.asarray(x[high],dtype=np.float64)-mean)@directions
    failure_scores=(ff-mean)@directions
    records=[]
    for i,expert in enumerate(experts):
        if count[i]<4:continue
        ww=w[:,i];ess=float(count[i]**2/max(float(ww@ww),1e-12))
        selected=fi[ww>.25]
        session_count=len({rows[j]['session'] for j in selected})
        low=failure_scores[:,i];positive=np.average(low,weights=ww)
        gap=positive-high_scores[:,i].mean()
        v=.5*(np.average((low-positive)**2,weights=ww)+high_scores[:,i].var())
        standardized=float(gap/np.sqrt(max(float(v),1e-20)))
        record=dict(expert,source_cell=cell['cell'],ess=ess,weighted_cases=float(count[i]),
                    dominant_sessions=session_count,training_auc=weighted_auc(high_scores[:,i],low,ww),
                    training_standardized_gap=standardized,actual_repair_not_evaluated=True,
                    candidate_only=True,no_independent_effect_claim=True)
        records.append(record)
    result=dict(status='COMPLETE',time=stamp(),cell=cell['cell'],block=cell['block'],group=cell['group'],
                dimension=x.shape[1],source_sha256=cell['sha256'],experts=records,
                success_reference_cases=len(all_high),high_descriptor_sample=len(high),
                selection_role='Training proposals; preserve per-layer and operator-diverse rollout coverage.',
                test_accessed=False,validation_accessed=False)
    target=ROOT/'analysis/group_proposals'/(cell['cell']+'.json');atomic(target,result)
    return dict(path=str(target.relative_to(ROOT)),experts=len(records))
