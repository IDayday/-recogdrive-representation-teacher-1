"""Read-only observed-draw stability strata for locked natural evaluations.

No new inference, true-score routing or selection. These finite observed draws
do not establish a permanent stable/unstable type for a scene.
"""
from r2_common import *


def run(task):
    import numpy as np
    from r2_natural_assessment_v2 import metrics
    path=ROOT/task['assessment'];d=read(path);assert d['mode'] in ['engineering','validation','test'];assert sha(ROOT/d['matrix'])==d['matrix_sha256'] and sha(ROOT/d['rows'])==d['rows_sha256'] and sha(ROOT/d['pack'])==d['pack_sha256'];lock=read(ROOT/d['lock'])
    if d['mode']!='engineering':assert lock['status']=='FROZEN_BEFORE_CONFIRMATION'
    if d['mode']=='test':assert lock['final_test_selection_frozen']
    rows=read(ROOT/d['rows']);pack=read(ROOT/d['pack'])
    with np.load(ROOT/d['matrix']) as z:score=np.array(z['scores']);panel=np.array(z['panel']);arms=list(z['arms']);noises=np.array(z['seeds'])
    assert np.isfinite(score).all() and score.dtype==np.float64 and len(panel)==d['cases'] and noises.tolist()==d['noise_indices'];base=score[:,arms.index('baseline')];n=len(panel);S=len(noises);sessions=[rows[int(i)]['session'] for i in panel];all_F=np.all(base[:,:,0]<.7,axis=1);all_H=np.all(base[:,:,0]>.9,axis=1);first_F=base[:,0,0]<.7;first_H=base[:,0,0]>.9
    strata=dict(observed_all_draws_failure=all_F,observed_all_draws_high=all_H,S0_failure_with_later_nonfailure=first_F&~all_F,S0_high_with_later_nonhigh=first_H&~all_H,S0_intermediate=~first_F&~first_H);assert np.all(np.stack(list(strata.values())).sum(0)==1)
    def summarize(after,mask):
        count=int(mask.sum())
        if not count:return dict(cases=0,population_mass=0.)
        own_sessions=[s for s,m in zip(sessions,mask) if m];b=base[mask];a=after[mask];result=metrics(b,a,own_sessions,task.get('bootstrap_samples',2000));session_count=len(set(own_sessions))
        if session_count<2:result['session_bootstrap_95']=None
        result.update(population_mass=count/n,sessions=session_count,global_mean_gain_contribution=count/n*result['mean_PDMS_gain'],nonfailure_every_observed_draw=int(np.sum(np.all(a[:,:,0]>=.7,axis=1))),nonfailure_some_observed_draw=int(np.sum(np.any(a[:,:,0]>=.7,axis=1))),high_every_observed_draw=int(np.sum(np.all(a[:,:,0]>.9,axis=1))),high_some_observed_draw=int(np.sum(np.any(a[:,:,0]>.9,axis=1))),newly_nonhigh_in_any_draw=int(np.sum(np.any((b[:,:,0]>.9)&(a[:,:,0]<=.9),axis=1))),newly_failure_in_any_draw=int(np.sum(np.any((b[:,:,0]>=.7)&(a[:,:,0]<.7),axis=1))))
        if S>1:
            repaired=(b[:,0,0]<.7)&(a[:,0,0]>=.7);repaired_high=(b[:,0,0]<.7)&(a[:,0,0]>.9);result.update(S0_repaired_atleast70=int(repaired.sum()),S0_repair_then_later_failure=int(np.sum(repaired&np.any(a[:,1:,0]<.7,axis=1))),S0_repaired_over90=int(repaired_high.sum()),S0_over90_repair_then_later_failure=int(np.sum(repaired_high&np.any(a[:,1:,0]<.7,axis=1))),S0_over90_repair_then_later_nonhigh=int(np.sum(repaired_high&np.any(a[:,1:,0]<=.9,axis=1))))
        return result
    results={}
    for config in pack['policies']:
        ident=config['id'];after=score[:,arms.index(ident)];actual={name:summarize(after,m) for name,m in strata.items()};assert abs(sum(v.get('global_mean_gain_contribution',0.) for v in actual.values())-d['results'][ident]['mean_PDMS_gain'])<1e-9;item=dict(actual_policy=actual)
        if config['kind']!='Base' and pack.get('include_raw_experts',True):
            policy=read(ROOT/config['policy']);parts=policy['configuration']['model']['parts'] if config['kind'] in ['joint','finite'] else policy['parts'];pool=score[:,[arms.index('baseline')]+[arms.index('candidate_'+p['id']) for p in parts]];choice=pool[:,:,:,0].argmax(1);oracle=pool[np.arange(n)[:,None],choice,np.arange(S)[None,:]];assert np.all(oracle[:,:,0]>=base[:,:,0]);item['same_policy_K_arm_privileged_oracle']={name:summarize(oracle,m) for name,m in strata.items()}
        results[ident]=item
    folder=ROOT/'analysis/frozen_stability_diagnostics'/task['id'];folder.mkdir(parents=True,exist_ok=False);record=dict(status='ENGINEERING_ONLY' if d['mode']=='engineering' else 'LOCKED_NATURAL_OBSERVED_STABILITY_DIAGNOSTICS',time=stamp(),task=task,mode=d['mode'],assessment=task['assessment'],assessment_sha256=sha(path),matrix_sha256=d['matrix_sha256'],cases=n,noise_draws=S,noise_indices=noises.tolist(),stratum_counts={k:int(m.sum()) for k,m in strata.items()},results=results,
        scope='Finite observed Base draws define the strata. Not permanent scene types. All deployment choices were frozen before these outcomes. Conditional strata are descriptive decompositions, not new primary hypothesis tests or tuning data.',
        same_scenes_and_draws_for_policy_and_own_K_arm_oracle=True,never_union_other_roles_or_fit_candidates=True,no_new_inference_or_scoring=True,noise_draws_not_independent_scenes=True,bootstrap_insufficient_sessions_reported_as_null=True,mean_gain_contributions_sum_to_primary=True)
    atomic(folder/'SUMMARY.json',record);return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),cases=n,stratum_counts=record['stratum_counts'])
