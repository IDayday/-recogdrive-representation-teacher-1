"""Own-K capacity diagnosis with one S0 choice held fixed across noises.

The original S1S2_fixed_policy endpoint fixes the bank, but reselects its
Oracle candidate separately for each noise. This additional endpoint fixes
the actual candidate, including Base, and pools multiplicity with the original
32 comparisons. All results remain privileged single-exploration-fold evidence.
"""
from r2_common import *


def main():
    setup('capacity_fixed_candidate_transfer')
    import numpy as np
    from r2_bank_potential import metrics
    original=read(ROOT/'analysis/expert_capacity_control/SUMMARY.json')
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    response=read(ROOT/original['response']);assert sha(ROOT/response['matrix'])==response['matrix_sha256']
    point=read(ROOT/response['point'])
    with np.load(ROOT/response['matrix']) as z:
        ii=np.array(z['global_indices']);ids=list(z['arm_ids']);scores=np.array(z['scores'])
    assert ids[0]=='baseline'
    mask=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==0 for r in rows])
    classes=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));pop=np.array([np.sum(mask&(q<.7)),np.sum(mask&(q>.9)),np.sum(mask&(q>=.7)&(q<=.9))]);counts=np.bincount(classes,minlength=3)
    weights=pop[classes]/counts[classes];weights/=weights.sum();base=scores[:,0];results=[];values={}
    stable=np.all(base[:,:,0]<.7,axis=1)
    for bank in point['banks']:
        assert sha(ROOT/bank['path'])==bank['sha256']
        for role,parts in bank['policies'].items():
            allowed=['baseline']+parts;actual=scores[:,[ids.index(v) for v in allowed]]
            choice=actual[:,:,0,0].argmax(1)
            fixed=actual[np.arange(len(ii)),choice]
            mean_choice=actual[:,:,:,0].mean(2).argmax(1)
            fixed_all=actual[np.arange(len(ii)),mean_choice]
            key=bank['id']+'_'+role;values[key]=fixed
            results.append(dict(id=key,rank=bank['rank'],budget_factor=bank['budget_factor'],role=role,K=3,
                own_candidate_ids=parts,S0_fixed_candidate_by_noise=[metrics(fixed[:,n],base[:,n],weights) for n in range(3)],
                all_noise_privileged_scene_fixed_by_noise=[metrics(fixed_all[:,n],base[:,n],weights) for n in range(3)],
                S0_choice_counts={v:int(np.sum(choice==j)) for j,v in enumerate(allowed)},
                stable_failure_cases=int(stable.sum()),stable_failure_conditional_gain_by_noise=((fixed[stable,:,0]-base[stable,:,0]).mean(0)*100).tolist(),
                interpretation='A true-score S0 winner is reused on S1/S2; still privileged, not an observable router.'))
    sessions=sorted({rows[int(i)]['session'] for i in ii});membership=np.array([sessions.index(rows[int(i)]['session']) for i in ii]);columns=[];comparisons=[]
    for r in results:
        if r['rank']==32 and r['budget_factor']==1:continue
        ref='capacity_r32_b1_'+r['role']
        columns.append((values[r['id']][:,1:,0]-values[ref][:,1:,0]).mean(1)*100)
        comparisons.append(dict(variant=r['id'],reference=ref,endpoint='S0_fixed_actual_candidate_S1S2_mean'))
    matrix=np.stack(columns,1);cluster=np.zeros((len(sessions),len(comparisons)));mass=np.zeros(len(sessions))
    np.add.at(cluster,membership,matrix*weights[:,None]);np.add.at(mass,membership,weights);observed=cluster.sum(0)
    rng=np.random.default_rng(2026101891);boot=[];extreme=np.zeros(len(comparisons),int)
    for start in range(0,10000,250):
        pick=rng.integers(len(sessions),size=(250,len(sessions)));boot.append(cluster[pick].sum(1)/mass[pick].sum(1)[:,None])
    boot=np.concatenate(boot)
    for start in range(0,19999,500):
        n=min(500,19999-start);sign=rng.integers(2,size=(n,len(sessions)))*2-1
        extreme+=np.sum(np.abs(sign@cluster)>=np.abs(observed)[None]-1e-12,axis=0)
    p=(extreme+1)/20000
    joined=np.r_[np.array([c['approximate_session_signflip_p'] for c in original['paired_comparisons']]),p]
    adjusted=np.zeros(len(joined));previous=0.
    for rank,index in enumerate(np.argsort(joined)):
        previous=max(previous,min(1.,(len(joined)-rank)*joined[index]));adjusted[index]=previous
    for j,c in enumerate(comparisons):
        c.update(mean_difference=float(observed[j]),fixed_sampling_weight_session_bootstrap95=np.quantile(boot[:,j],[.025,.975]).tolist(),approximate_session_signflip_p=float(p[j]),Holm_p_all48=float(adjusted[32+j]))
    old=[dict(c,Holm_p_all48=float(adjusted[j])) for j,c in enumerate(original['paired_comparisons'])]
    path=ROOT/'analysis/expert_capacity_control/FIXED_CANDIDATE_TRANSFER.json';assert not path.exists()
    atomic(path,dict(status='COMPLETE_FIXED_ACTUAL_CANDIDATE_TRANSFER_DIAGNOSTIC',time=stamp(),original_summary_sha256=sha(ROOT/'analysis/expert_capacity_control/SUMMARY.json'),
        response=original['response'],response_sha256=sha(ROOT/original['response']),cases=len(ii),sessions=len(sessions),results=results,
        fixed_candidate_comparisons=comparisons,original_per_draw_oracle_comparisons_pooled=old,
        multiplicity=dict(total_hypotheses=48,original=32,new_fixed_transfer=16,bootstrap=10000,signflip=19999),
        original_endpoint_clarification='S1S2_fixed_policy fixes the candidate bank; its true-score winner is reselected per noise. It does not fix the chosen candidate.',
        scope='Single exploration-fold privileged diagnosis; approximate fixed-sampling-weight session inference. No deployment gain or validation/test observation.',validation_accessed=False,test_accessed=False))
    print(json.dumps(dict(status='COMPLETE',path=str(path.relative_to(ROOT)),cases=len(ii),sessions=len(sessions),comparisons=48)))


if __name__=='__main__':main()
