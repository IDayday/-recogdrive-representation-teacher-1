"""Apply a frozen critic rule, then look up actual independent candidate outcomes."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_token_policy_select import choices,matrices
    from r2_expert_space import save_npz
    point=read(ROOT/task['point']);assert point['mode']=='heldout';policy_path=ROOT/point['policy'];assert sha(policy_path)==point['policy_sha256'];policy=read(policy_path)
    data,lineage=matrices(point,task['stage']);assert data['predicted'].shape[1]==1
    # choices() has no true score argument. Outcomes are accessed after routing.
    choice=choices(data['predicted'][:,0],policy['critic']['risk_penalty'],policy['critic']['threshold'])
    after=data['scores'][np.arange(len(choice)),choice];base=data['scores'][:,0];trajectory=data['trajectory'][np.arange(len(choice)),choice]
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);ii=data['global_indices'];held=policy['heldout_fold']
    mask=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==held for r in rows]);assert held>=0 and np.all(mask[ii])
    classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
    populations=[np.sum(mask&(quality<.7)),np.sum(mask&(quality>.9)),np.sum(mask&(quality>=.7)&(quality<=.9))]
    w=np.asarray([populations[c]/counts[c] for c in classes]);w/=w.sum();delta=after[:,0]-base[:,0]
    metrics=dict(weighted_pdms_gain=float(w@delta*100),enriched_mean_pdms_gain=float(delta.mean()*100),
        net_collision=int(np.sum(after[:,1]<1)-np.sum(base[:,1]<1)),net_offroad=int(np.sum(after[:,2]<1)-np.sum(base[:,2]<1)),net_zero=int(np.sum(after[:,0]==0)-np.sum(base[:,0]==0)),
        net_TTC=int(np.sum(after[:,3]<1)-np.sum(base[:,3]<1)),net_failures=int(np.sum(after[:,0]<.7)-np.sum(base[:,0]<.7)),
        repaired90=int(np.sum((base[:,0]<.7)&(after[:,0]>.9))),lost_high=int(np.sum((base[:,0]>.9)&(after[:,0]<=.9))),active_fraction=float(w@(choice>0)))
    folder=ROOT/'analysis/token_policy_cv';path=folder/point['id'];hashed=save_npz(path.with_suffix('.npz'),global_indices=ii,seeds=data['seeds'],base_scores=base,selected_scores=after,choice=choice,trajectory=trajectory,weights=w)
    atomic(path.with_suffix('.json'),dict(status='HELDOUT_POLICY_EVALUATED',time=stamp(),policy=point['policy'],policy_sha256=point['policy_sha256'],system=policy['system'],role=policy['role'],wave=policy['wave'],fit_seed=policy['fit_seed'],heldout_fold=held,
        metrics=metrics,matrix=str(path.with_suffix('.npz').relative_to(ROOT)),matrix_sha256=hashed,sources=lineage,
        evaluated_cases=len(set(ii.tolist())),examples=len(ii),native_sample_count=len(set(data['seeds'].tolist())),
        actual_generated_candidate_outcomes_reused=True,heldout_outcomes_not_used_to_route=True,
        population_scope='All held-fold S0 failures and predeclared success/intermediate sample; weighted estimate, not complete natural population.',validation_accessed=False,test_accessed=False))
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),metrics=metrics)
