"""Locked-family paired session uncertainty, multiplicity, and fit consistency.

Prepared before natural confirmation. Averaging independent fitted policies is a
stability summary of fits, never a trajectory mixture or a deployable ensemble.
"""
from r2_common import *


def run(task):
    import numpy as np
    summary=read(ROOT/task['assessment']);assert summary['mode'] in ['engineering','validation','test'];assert sha(ROOT/summary['matrix'])==summary['matrix_sha256']
    pack=read(ROOT/summary['pack']);assert sha(ROOT/summary['pack'])==summary['pack_sha256'];rows=read(ROOT/summary['rows']);assert sha(ROOT/summary['rows'])==summary['rows_sha256']
    with np.load(ROOT/summary['matrix']) as z:score=np.array(z['scores']);arms=list(z['arms']);panel=np.array(z['panel'])
    base=score[:,arms.index('baseline'),:,0];specs=[c for c in pack['policies'] if c['kind']!='Base'];individual=[];hypotheses=[]
    for config in specs:
        delta=(score[:,arms.index(config['id']),:,0]-base)*100
        item=dict(id=config['id'],kind='single_frozen_policy',structure=config.get('structure_id',config['id']),role=config.get('selection_role','engineering_unspecified'),fit_replicate=config.get('fit_replicate',0),delta=delta)
        individual.append(item);hypotheses.append(item)
    groups={}
    for item in individual:groups.setdefault((item['structure'],item['role']),[]).append(item)
    for (structure,role),items in groups.items():
        if len(items)<2:continue
        assert len({v['fit_replicate'] for v in items})==len(items)
        hypotheses.append(dict(id='fit_mean_'+digest(dict(structure=structure,role=role))[:16],kind='average_over_independent_fits_not_deployable',structure=structure,role=role,
            fit_replicates=[v['fit_replicate'] for v in items],member_policies=[v['id'] for v in items],complete_three_fits=len(items)>=3,delta=np.stack([v['delta'] for v in items]).mean(0)))
    names=sorted({rows[int(i)]['session'] for i in panel});mapping={name:j for j,name in enumerate(names)};ss=np.zeros((len(names),len(hypotheses)));counts=np.zeros(len(names))
    for j,index in enumerate(panel):counts[mapping[rows[int(index)]['session']]]+=1
    for k,h in enumerate(hypotheses):
        scene=h['delta'].mean(1)
        for j,index in enumerate(panel):ss[mapping[rows[int(index)]['session']],k]+=scene[j]
    assert counts.sum()==len(panel);observed=ss.sum(0)/counts.sum();B=task.get('bootstrap_samples',10000);P=task.get('permutation_samples',19999);rng=np.random.default_rng(2026101817);boot=[];extreme=np.zeros(len(hypotheses),dtype=int)
    for start in range(0,B,100):
        n=min(100,B-start);pick=rng.integers(len(names),size=(n,len(names)));boot.append(ss[pick].sum(1)/counts[pick].sum(1)[:,None])
    boot=np.concatenate(boot);m=len(hypotheses)
    for start in range(0,P,500):
        n=min(500,P-start);signs=rng.integers(2,size=(n,len(names)))*2-1;permuted=signs@ss/counts.sum();extreme+=np.sum(np.abs(permuted)>=np.abs(observed)[None]-1e-12,axis=0)
    pvalues=(extreme+1)/(P+1);order=np.argsort(pvalues);adjusted=np.zeros(m);previous=0.
    for rank,k in enumerate(order):previous=max(previous,min(1.,(m-rank)*pvalues[k]));adjusted[k]=previous
    results=[]
    for k,h in enumerate(hypotheses):
        delta=h.pop('delta');pointwise=np.quantile(boot[:,k],[.025,.975]);simultaneous=np.quantile(boot[:,k],[.05/(2*m),1-.05/(2*m)])
        value=dict(h,mean_PDMS_gain=float(observed[k]),gain_by_noise=delta.mean(0).tolist(),session_bootstrap_95=pointwise.tolist(),Bonferroni_bootstrap_95_family=simultaneous.tolist(),session_signflip_two_sided_p=float(pvalues[k]),Holm_p=float(adjusted[k]),
            every_observed_noise_nonnegative=bool(np.all(delta.mean(0)>=0)),multiplicity_adjusted_positive=bool(adjusted[k]<.05 and pointwise[0]>0))
        if h['kind'].startswith('average_'):
            members=[v for v in individual if v['id'] in h['member_policies']];value['mean_gain_by_fit']={v['id']:summary['results'][v['id']]['mean_PDMS_gain'] for v in members};value['every_fitted_policy_positive']=all(v>0 for v in value['mean_gain_by_fit'].values());value['every_fitted_policy_safety_all_noise']=all(summary['results'][v['id']]['safety_all_noise'] for v in members)
        else:value['safety_all_noise']=summary['results'][h['id']]['safety_all_noise']
        results.append(value)
    folder=ROOT/'analysis/confirmation_statistics'/task['id'];folder.mkdir(parents=True,exist_ok=False);atomic(folder/'SUMMARY.json',dict(status='ENGINEERING_ONLY' if summary['mode']=='engineering' else 'LOCKED_CONFIRMATION_STATISTICS',time=stamp(),task=task,assessment=task['assessment'],assessment_sha256=sha(ROOT/task['assessment']),mode=summary['mode'],cases=len(panel),sessions=len(names),hypotheses=m,results=results,bootstrap_samples=B,signflip_samples=P,
        family='Every frozen non-Base policy and every predeclared across-fit group in this pack, including negative and identity-like outcomes; never only winners.',
        assumptions='Sessions are resampling clusters. Sign-flip p values use an approximate exchangeability/symmetry assumption; Holm is applied across the entire locked family. Bootstrap family intervals use Bonferroni-adjusted tails and are approximate.',
        fit_mean_not_a_deployment_ensemble=True,noise_repetitions_never_counted_as_independent_scenes=True,does_not_reselect_or_refit_policies=True));return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),hypotheses=m)
