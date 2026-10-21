"""Combine already-computed per-fold candidate/observed-stability diagnostics.

No new model calls, outcome selection, fitted spaces or uncertainty claims.
Each policy uses its own K candidates; cached unions are never pooled together.
"""
from r2_common import *


def run(task):
    import numpy as np
    from r2_extended_cv_review import population
    rows,classes,fold,explore,counts=population();total=int(counts.sum());inputs=[]
    for spec in task['inputs']:
        assert sha(ROOT/spec['potential'])==spec['potential_sha256'] and sha(ROOT/spec['stability'])==spec['stability_sha256'];a=read(ROOT/spec['potential']);b=read(ROOT/spec['stability']);assert a['system']==b['system']==task['system'] and a['heldout_fold']==b['heldout_fold']==spec['fold'] and a['source_bank']==b['source_bank'] and a['matrix_sha256']==b['source_matrix_sha256'];inputs.append((spec['fold'],a,b))
    assert sorted(h for h,a,b in inputs)==list(range(5));keys=set(inputs[0][1]['roles']);assert all(set(a['roles'])==keys and set(b['comparisons'])==keys for h,a,b in inputs);output={}
    for key in sorted(keys):
        oracle=np.zeros(3);safe=np.zeros(3);fixed=np.zeros(3);scene=np.zeros(3);repair=np.zeros(3,int);stableN=0;stableBase=np.zeros(3);stableOracle=np.zeros(3);stableContribution=np.zeros(3);stableFixedRepair=np.zeros(3,int);stableAll=0;stableBase3=0.;modules=[];raw_forcing=[];sources=[]
        for held,a,b in inputs:
            mass=float(counts[held].sum()/total);role=a['roles'][key];modules.append(role['nonzero_modules']);oracle+=mass*np.array([v['metrics']['standardized_pdms_gain'] for v in role['draw_oracle']]);safe+=mass*np.array([v['metrics']['standardized_pdms_gain'] for v in role['strict_per_output_safety_oracle']]);fixed+=mass*np.array([v['S0_fixed_expert']['standardized_pdms_gain'] for v in role['scene_fixed_transfer']]);scene+=mass*np.array([v['all_three_noise_privileged_fixed_expert']['standardized_pdms_gain'] for v in role['scene_fixed_transfer']]);repair+=np.array([v['metrics']['repaired90'] for v in role['draw_oracle']])
            raw_forcing.extend(dict(fold=held,candidate=c,gain_by_noise=[v['unconditional']['standardized_pdms_gain'] for v in values]) for c,values in role['fixed_raw_candidates'].items());s=b['comparisons'][key]['observed_all3_failure'];n=s['cases'];stableN+=n
            if n:
                stableBase+=n*np.array(s['Base_mean_PDMS_by_draw']);stableOracle+=n*np.array(s['repair_oracle_PDMS_by_draw']);stableContribution+=mass*np.array(s['global_standardized_gain_contribution_by_draw']);stableFixedRepair+=np.array(s['S0_fixed_expert_repaired90_by_draw']);stableAll+=s['S0_fixed_expert_all3_above90'];stableBase3+=n*s['Base_three_draw_oracle_PDMS']
            sources.append(dict(fold=held,bank=a['source_bank'],matrix_sha256=a['matrix_sha256'],candidate_ids=role['candidate_ids']))
        output[key]=dict(nonzero_modules_by_fold=modules,identity_additional=True,candidate_oracle_standardized_gain_by_noise=oracle.tolist(),strict_per_output_safety_oracle_gain_by_noise=safe.tolist(),S0_privileged_fixed_expert_gain_by_noise=fixed.tolist(),all_three_noise_privileged_fixed_expert_gain_by_noise=scene.tolist(),raw_sample_repaired90_by_noise=repair.tolist(),unconditional_each_candidate_by_fold=raw_forcing,
            observed_all3_failure=dict(cases=stableN,Base_conditional_PDMS_by_draw=(stableBase/max(stableN,1)).tolist(),candidate_oracle_conditional_PDMS_by_draw=(stableOracle/max(stableN,1)).tolist(),conditional_gain_by_draw=((stableOracle-stableBase)/max(stableN,1)).tolist(),global_standardized_gain_contribution_by_draw=stableContribution.tolist(),S0_fixed_candidate_repair90_by_draw=stableFixedRepair.tolist(),S0_fixed_candidate_all3_over90=stableAll,Base3_privileged_oracle_conditional_PDMS=stableBase3/max(stableN,1),Base3_opportunities_matched_only_when_K2=True),sources=sources)
    folder=ROOT/'analysis/held_fivefold_potential'/task['id'];folder.mkdir(parents=True,exist_ok=False);atomic(folder/'SUMMARY.json',dict(status='COMPLETE_FIVEFOLD_PRIVILEGED_CANDIDATE_DIAGNOSTIC',time=stamp(),task=task,system=task['system'],folds=list(range(5)),sampled_cases=sum(a['cases'] for h,a,b in inputs),natural_standardization_population=total,roles=output,
        scope='Complete outer-fold candidate diagnostics, class-standardized enriched panels. Not unbiased full-natural-population performance, not a deployable policy or theoretical upper bound. StableF means failure in these three observed Base draws only.',
        same_policy_K_parts_never_other_roles_union=True,duplicate_tier_candidate_sets_not_independent_experiments=True,three_noises_not_independent_scenes=True,no_new_model_trajectory_or_scoring=True,validation_accessed=False,test_accessed=False));return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),system=task['system'])
