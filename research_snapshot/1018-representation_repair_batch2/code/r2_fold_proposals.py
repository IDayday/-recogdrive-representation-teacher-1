"""Whole-system CV location proposals: every label-dependent fit excludes its fold."""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=5)
def inputs(held):
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    explore=np.array([r['subset']=='exploration' for r in rows]);train=explore&(fold!=held)
    failures=np.flatnonzero(train&(q<.7))
    systems=read(ROOT/'analysis/initial_groups'/f'fold{held}'/'COMPLETE.json')['initialization_systems']
    weights=[];experts=[]
    for system in systems:
        with np.load(ROOT/system['path']) as z:
            assert np.array_equal(z['global_indices'],failures)
            responsibility=np.array(z['responsibility'],dtype=np.float64)
        for expert in range(system['K']):
            weights.append(responsibility[:,expert])
            experts.append(dict(system=system['id'],K=system['K'],fit_seed=system['fit_seed'],expert=expert,
                      responsibility_path=system['path'],responsibility_sha256=system['sha256']))
    high_order=np.array(sorted(np.flatnonzero(train&(q>.9)),key=lambda i:digest(dict(token=rows[i]['token'],proposal_high=20261018))))
    return rows,q,explore,train,failures,np.stack(weights,1),experts,high_order,fold


def run(task):
    import numpy as np
    from r2_group_proposal import weighted_auc
    held=task['heldout_fold'];rows,q,explore,train,failure,weights,experts,high_order,fold=inputs(held)
    cell=task['cell'];x=np.load(cell['absolute_path'],mmap_mode='r');valid=np.isfinite(x[:,0])
    fi=failure[valid[failure]];all_high=np.flatnonzero(train&(q>.9)&valid)
    target=ROOT/'analysis/fold_proposals'/f'fold{held}'/(cell['cell']+'.json')
    if min(len(fi),len(all_high))<24:
        result=dict(status='INELIGIBLE',cell=cell['cell'],heldout_fold=held)
        atomic(target,result);return result
    # Existing full-training sufficient statistics minus this held-out session
    # fold are algebraically training-only. No held-out response is used to rank.
    moment=OLD/('vlm_semantic_v2' if cell['group'].endswith('_v2') else 'vlm_repair_v1')/'moments'/(cell['cell']+'.npz')
    excluded=np.flatnonzero(explore&(fold==held)&(q>.9)&valid)
    with np.load(moment) as z:
        assert int(z['ns'])==len(all_high)+len(excluded)
        ss=np.array(z['ss'],dtype=np.float64);squared=np.diag(z['gs']).copy()
    for start in range(0,len(excluded),2048):
        a=np.asarray(x[excluded[start:start+2048]],dtype=np.float64)
        ss-=a.sum(0);squared-=np.square(a).sum(0)
    mean=ss/len(all_high);variance=np.maximum(squared/len(all_high)-mean**2,1e-12)
    ff=np.asarray(x[fi],dtype=np.float64);w=weights[valid[failure]]
    count=w.sum(0);means=ff.T@w/np.maximum(count,1e-12)
    variances=np.square(ff).T@w/np.maximum(count,1e-12)-means**2
    directions=(means-mean[:,None])/np.maximum(.5*(variance[:,None]+variances),1e-8)
    high=high_order[valid[high_order]][:2048]
    hs=(np.asarray(x[high],dtype=np.float64)-mean)@directions;fs=(ff-mean)@directions
    records=[]
    for j,expert in enumerate(experts):
        if count[j]<4:continue
        ww=w[:,j];ess=float(count[j]**2/max(float(ww@ww),1e-12))
        sessions=len({rows[i]['session'] for i in fi[ww>.25]})
        positive=np.average(fs[:,j],weights=ww);gap=positive-hs[:,j].mean()
        variance=.5*(np.average((fs[:,j]-positive)**2,weights=ww)+hs[:,j].var())
        records.append(dict(expert,source_cell=cell['cell'],ess=ess,weighted_cases=float(count[j]),
                  dominant_sessions=sessions,training_auc=weighted_auc(hs[:,j],fs[:,j],ww),
                  training_standardized_gap=float(gap/np.sqrt(max(float(variance),1e-20))),
                  heldout_fold=held,candidate_only=True,actual_repair_not_evaluated=True))
    result=dict(status='COMPLETE',time=stamp(),cell=cell['cell'],block=cell['block'],group=cell['group'],
                heldout_fold=held,experts=records,source_sha256=cell['sha256'],success_reference_cases=len(all_high),
                train_only_label_dependent_selection=True,validation_fitted=False,test_accessed=False)
    atomic(target,result);return dict(path=str(target.relative_to(ROOT)),experts=len(records))
