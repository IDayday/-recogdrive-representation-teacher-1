"""Synthetic arithmetic check of the unexercised three-fit statistics branch.

These are explicitly synthetic scores, not model runs or scientific evidence.
No final model, real-scene result, selection or cloud process is touched.
"""
from r2_common import *


def main():
    import numpy as np
    from r2_confirmation_statistics import run
    folder=ROOT/'provenance/statistics_synthetic_fitgroup_v1';folder.mkdir(parents=True,exist_ok=False)
    rows=[dict(token='SYNTHETIC_CASE_'+str(j),session='SYNTHETIC_SESSION_'+str(j//2)) for j in range(4)];rows_path=folder/'rows.json';atomic(rows_path,rows)
    configs=[dict(id='SYNTHETIC_FIT_'+str(j),kind='hard',structure_id='SYNTHETIC_STRUCTURE',selection_role='synthetic_arithmetic_only',fit_replicate=j) for j in range(3)];pack_path=folder/'pack.json';atomic(pack_path,dict(policies=configs,synthetic_not_model_outputs=True))
    arms=['baseline']+[c['id'] for c in configs];score=np.ones((4,4,2,7));score[:,:,:,0]=.9
    for j in range(3):score[:,j+1,:,0]=.9+.01*(j+1)
    matrix=folder/'synthetic_scores.npz';np.savez(matrix,scores=score,arms=np.asarray(arms),panel=np.arange(4));assessment=folder/'synthetic_assessment.json'
    results={c['id']:dict(mean_PDMS_gain=float((score[:,j+1,:,0]-score[:,0,:,0]).mean()*100),safety_all_noise=True) for j,c in enumerate(configs)}
    atomic(assessment,dict(mode='engineering',synthetic_not_model_outputs=True,matrix=str(matrix.relative_to(ROOT)),matrix_sha256=sha(matrix),pack=str(pack_path.relative_to(ROOT)),pack_sha256=sha(pack_path),rows=str(rows_path.relative_to(ROOT)),rows_sha256=sha(rows_path),results=results))
    task=dict(id='SYNTHETIC_FITGROUP_ARITHMETIC_v1',assessment=str(assessment.relative_to(ROOT)),bootstrap_samples=2000,permutation_samples=1999);output=run(task);record=read(ROOT/output['path']);assert record['mode']=='engineering' and record['hypotheses']==4
    group=next(r for r in record['results'] if r['kind']=='average_over_independent_fits_not_deployable');assert group['complete_three_fits'] and group['fit_replicates']==[0,1,2] and abs(group['mean_PDMS_gain']-2)<1e-10 and np.allclose(group['gain_by_noise'],[2,2]);assert group['every_fitted_policy_positive'] and group['every_fitted_policy_safety_all_noise'];assert np.allclose(sorted(group['mean_gain_by_fit'].values()),[1,2,3]);assert group['Holm_p']>=group['session_signflip_two_sided_p'] and not group['multiplicity_adjusted_positive']
    proof=dict(status='PASS_SYNTHETIC_ARITHMETIC_ONLY',time=stamp(),synthetic_not_model_or_research_result=True,observed_fit_mean=group['mean_PDMS_gain'],expected_fit_mean=2.,group_has_three_fits=True,all_four_hypotheses_including_fit_mean=True,fit_safety_aggregation_verified=True,two_session_uncertainty_does_not_claim_significance=True,output=output,output_sha256=sha(ROOT/output['path']),new_model_or_scoring_runs=0)
    atomic(ROOT/'provenance/CONFIRMATION_THREE_FIT_BRANCH_SYNTHETIC_CHECK.json',proof);print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':main()
