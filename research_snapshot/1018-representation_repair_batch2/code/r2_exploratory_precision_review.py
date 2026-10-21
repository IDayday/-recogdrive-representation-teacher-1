"""Resolve Monte Carlo p-value granularity for the full exploratory family.

Reconstruct exact existing session contributions, preserving effect estimands.
The result stays exploratory: more permutations do not create new held data or
make the session sign-symmetry assumption exact. No model or cloud actions.
"""
from r2_common import *
import argparse


def main(args):
    setup('exploratory_precision_review',threads=args.threads)
    import numpy as np
    from threadpoolctl import threadpool_limits
    from r2_extended_cv_review import population
    snapshot=read(ROOT/args.snapshot);assert sha(ROOT/snapshot['path'])==snapshot['sha256'];review=read(ROOT/snapshot['path'])
    complete=[r for r in review['recipes'] if r['complete_five_folds']]
    if args.engineering:complete=sorted(complete,key=lambda r:(r['method'],r['system'],r['policy']))[:12]
    keys={(r['method'],r['system'],r['policy']):j for j,r in enumerate(complete)};assert len(keys)==len(complete)>0
    rows,cls,fold,explore,pop=population();names=sorted({r['session'] for r in rows if r['subset']=='exploration'});sessions={v:j for j,v in enumerate(names)}
    cluster=np.zeros((len(names),len(keys)));coverage={k:set() for k in keys};sources=[]
    for info in review['sources']:
        response=read(ROOT/info['path']);point=read(ROOT/response['point']);held=point['heldout_fold'];stage=Path(response['task']['stage']).name;method=stage.replace('_cv_v1','').replace('_policy','')
        if point.get('kind'):method+='_'+point['kind']
        if not any(k[0]==method and k[1]==point['system'] for k in keys):continue
        assert sha(ROOT/response['matrix'])==response['matrix_sha256']==info['matrix_sha256']
        with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);arms=list(z['arm_ids']);scores=np.array(z['scores']);noise=np.array(z['seeds'])
        assert np.all(explore[ii]&(fold[ii]==held)) and list(noise)==[0,1,2]
        counts=np.bincount(cls[ii],minlength=3);assert np.all(counts>0)
        weight=pop[held,cls[ii]]/counts[cls[ii]]/pop.sum();sessionindex=np.array([sessions[rows[int(i)]['session']] for i in ii])
        for a,arm in enumerate(arms[1:],1):
            key=(method,point['system'],str(arm))
            if key not in keys:continue
            assert held not in coverage[key];coverage[key].add(held)
            contribution=(scores[:,a,:,0]-scores[:,0,:,0]).mean(1)*weight*100
            np.add.at(cluster[:,keys[key]],sessionindex,contribution)
        sources.append(dict(response=info['path'],matrix=response['matrix'],matrix_sha256=response['matrix_sha256']))
    assert all(v==set(range(5)) for v in coverage.values())
    observed=cluster.sum(0);reference=np.array([r['standardized_pdms_gain'] for r in complete]);assert np.allclose(observed,reference,rtol=0,atol=1e-10)
    protocol='config/EXPLORATORY_PRECISION_PROTOCOL_V1.json';config=read(ROOT/protocol)
    draws=4095 if args.engineering else max(config['minimum_sign_draws'],400*len(complete)-1)
    rng=np.random.default_rng(config['seed']);extreme=np.zeros(len(complete),np.int64);began=time.monotonic()
    directory=ROOT/'analysis/exploratory_precision'/('engineering_' if args.engineering else 'full_')/Path(snapshot['path']).parent.name;directory.mkdir(parents=True,exist_ok=False)
    # Common session signs preserve the dependence across related recipes;
    # Holm does not require independent p-values.
    with threadpool_limits(limits=args.threads):
        for start in range(0,draws,512):
            n=min(512,draws-start);signs=(rng.integers(2,size=(n,len(names)),dtype=np.int8)*2-1).astype(np.float64)
            simulated=signs@cluster
            extreme+=np.sum(np.abs(simulated)>=np.abs(observed)[None]-1e-12,axis=0)
            if start==0:
                for j in range(min(3,len(complete))):assert np.allclose(simulated[:,j],(signs*cluster[:,j]).sum(1),rtol=0,atol=1e-10)
            if start%(512*64)==0:atomic(directory/'LIVE.json',dict(time=stamp(),completed=start+n,draws=draws,recipes=len(complete),seconds=time.monotonic()-began))
    p=(extreme+1)/(draws+1);adjusted=np.zeros(len(p));previous=0.
    for order,index in enumerate(np.argsort(p)):previous=max(previous,min(1.,(len(p)-order)*p[index]));adjusted[index]=previous
    records=[]
    for j,r in enumerate(complete):records.append(dict(method=r['method'],system=r['system'],policy=r['policy'],standardized_pdms_gain=float(observed[j]),standardized_pdms_gain_by_noise=r['standardized_pdms_gain_by_noise'],approximate_safety_all_noise=r['approximate_safety_all_noise'],old_session_signflip_p=r['cluster_signflip_two_sided_p'],old_Holm_p=r['holm_p'],extreme_count=int(extreme[j]),session_signflip_p=float(p[j]),Holm_p=float(adjusted[j]),MonteCarlo_standard_error=float(np.sqrt(p[j]*(1-p[j])/(draws+1)))))
    summary=dict(status='ENGINEERING_ONLY_PARTIAL_FAMILY' if args.engineering else 'COMPLETE_FROZEN_SNAPSHOT_EXPLORATORY_PRECISION_REVIEW',time=stamp(),snapshot=snapshot,protocol=protocol,protocol_sha256=sha(ROOT/protocol),recipes=records,full_family_size=len(complete),sessions=len(names),session_sign_draws=draws,minimum_attainable_p=1/(draws+1),first_Holm_threshold=.05/len(complete),old_draws=review['bootstrap_samples'],old_minimum_attainable_p=1/(review['bootstrap_samples']+1),old_first_Holm_rejection_possible=1/(review['bootstrap_samples']+1)<=.05/len(complete),effects_match_previous_to_1e10=True,sources=sources,seconds=time.monotonic()-began,scope='Exact same existing full-fivefold effect estimand and full frozen snapshot family. Session sign-flip remains an exploratory symmetry approximation. High precision neither fixes adaptive selection nor supplies independent natural confirmation.',all_zero_andnegative_recipes_included=not args.engineering,validation_accessed=False,test_accessed=False)
    atomic(directory/'SUMMARY.json',summary)
    if not args.engineering:atomic(ROOT/'analysis/exploratory_precision/LATEST.json',dict(time=stamp(),path=str((directory/'SUMMARY.json').relative_to(ROOT)),sha256=sha(directory/'SUMMARY.json')))
    print(json.dumps(dict(status=summary['status'],path=str((directory/'SUMMARY.json').relative_to(ROOT)),recipes=len(complete),sign_draws=draws,seconds=summary['seconds'],exact_effects=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',default='analysis/extended_cv_reviews/LATEST.json');p.add_argument('--engineering',action='store_true');p.add_argument('--threads',type=int,default=8);main(p.parse_args())
