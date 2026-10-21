"""Matched three-trajectory S0 oracle control, using actual Base S0/S1/S2."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_bank_potential import metrics
    bank=read(ROOT/task['bank']);assert bank['mode']=='heldout';held=bank['heldout_fold'];point=read(ROOT/bank['point'])
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);mask=np.asarray([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==held for r in rows])
    with np.load(ROOT/bank['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);scores=np.array(z['scores']);seeds=np.array(z['seeds'])
    assert np.all(mask[ii]) and seeds.tolist()==[0,1,2];classes=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));counts=np.bincount(classes,minlength=3);population=np.asarray([np.sum(mask&(q<.7)),np.sum(mask&(q>.9)),np.sum(mask&(q>=.7)&(q<=.9))]);w=np.asarray([population[c]/counts[c] for c in classes]);w/=w.sum()
    base=scores[:,0,0];native_pool=scores[:,0];native_choice=native_pool[:,:,0].argmax(1);native=native_pool[np.arange(len(ii)),native_choice]
    native_metrics=metrics(native,base,w);output={}
    for configuration in point['policies']:
        policy=read(ROOT/configuration['policy']);parts=policy['parts']
        if len(parts)!=2:continue
        pick=[0]+[ids.index(p['id']) for p in parts];candidate=scores[:,pick,0];choice=candidate[:,:,0].argmax(1);repair=candidate[np.arange(len(ii)),choice]
        difference=(repair[:,0]-native[:,0])*100;names=sorted({rows[i]['session'] for i in ii});clusters=np.asarray([sum(w[j]*difference[j] for j,i in enumerate(ii) if rows[i]['session']==name) for name in names]);rng=np.random.default_rng(2026101811)
        boot=np.asarray([clusters[rng.integers(len(clusters),size=len(clusters))].sum() for _ in range(1000)]);ci=np.quantile(boot,[.025,.975]).tolist()
        output[configuration['id']]=dict(repair_candidates=3,Base_candidates=3,repair_S0_oracle=metrics(repair,base,w),Base_three_draw_oracle=native_metrics,
            repair_minus_Base_oracle_pdms_points=float(w@difference),session_cluster_fixed_weight_bootstrap_95=ci,
            repair_candidate_ids=['baseline']+[p['id'] for p in parts],Base_candidate_sampling_indices=[0,1,2])
    path=ROOT/'analysis/base_resampling_controls'/(task['id']+'.json');atomic(path,dict(status='HELD_SESSION_PRIVILEGED_MATCHED_S0_CONTROL',time=stamp(),system=bank['system'],heldout_fold=held,cases=len(ii),comparisons=output,
        source_bank=task['bank'],source_matrix_sha256=bank['matrix_sha256'],new_trajectory_generation=0,new_scoring=0,
        scope='K2 only, three whole trajectories each and the same S0 reference. Other repair noises are not independent episodes of this shared Base pool. Oracle control, not a trained Base-only selector.',
        population='Class-standardized session-balanced sampled panel; not full natural distribution.',higher_K_matched_budget_not_covered=True,validation_accessed=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)),comparisons=len(output))
