"""Posthoc trigger/selection envelopes of every completed frozen CV policy.

Only existing scores are reduced. No model, fitting, trajectory generation,
rescoring, candidate admission or validation/test access.
"""
from r2_common import *
from collections import defaultdict


def main():
    setup('frozen_privileged_envelope',threads=4)
    import numpy as np
    from r2_extended_cv_review import population
    pointer=read(ROOT/'provenance/final_confirmation/EXPLORATION_SNAPSHOT.json')
    assert sha(ROOT/pointer['path'])==pointer['sha256'];review=read(ROOT/pointer['path'])
    complete={(r['method'],r['system'],r['policy']):r for r in review['recipes'] if r['complete_five_folds']}
    rows,classes,fold,explore,pop=population();acc={};sources=[]
    def new():
        return dict(folds=set(),gain={k:np.zeros(3) for k in ['actual','perfect_failure_trigger','beneficial_only','S0_fixed_Base_or_policy_branch']},
            repairs={k:np.zeros((3,2),np.int64) for k in ['actual','perfect_failure_trigger','beneficial_only','S0_fixed_Base_or_policy_branch']},
            safety={k:np.zeros((3,3)) for k in ['actual','perfect_failure_trigger','beneficial_only','S0_fixed_Base_or_policy_branch']})
    for number,info in enumerate(review['sources']):
        response=read(ROOT/info['path']);point=read(ROOT/response['point']);held=point['heldout_fold']
        method=Path(response['task']['stage']).name.replace('_cv_v1','').replace('_policy','')
        if point.get('kind'):method+='_'+point['kind']
        if not any(k[0]==method and k[1]==point['system'] for k in complete):continue
        assert sha(ROOT/response['matrix'])==response['matrix_sha256']==info['matrix_sha256']
        with np.load(ROOT/response['matrix']) as z:
            ii=np.array(z['global_indices']);ids=list(z['arm_ids']);score=np.array(z['scores']);assert list(z['seeds'])==[0,1,2]
        assert np.all(explore[ii]&(fold[ii]==held));counts=np.bincount(classes[ii],minlength=3);assert np.all(counts>0)
        weights=pop[held,classes[ii]]/counts[classes[ii]]/pop.sum();base=score[:,0];failure=base[:,:,0]<.7
        for column,arm in enumerate(ids[1:],1):
            key=(method,point['system'],str(arm))
            if key not in complete:continue
            item=acc.setdefault(key,new());assert held not in item['folds'];item['folds'].add(held)
            after=score[:,column];fixed=(after[:,0,0]>base[:,0,0])[:,None]
            alternatives=dict(actual=after,perfect_failure_trigger=np.where(failure[:,:,None],after,base),
                beneficial_only=np.where((after[:,:,0]>base[:,:,0])[:,:,None],after,base),
                S0_fixed_Base_or_policy_branch=np.where(fixed[:,:,None],after,base))
            old_events=np.stack([base[:,:,1]<1,base[:,:,2]<1,base[:,:,0]==0],-1)
            for name,value in alternatives.items():
                item['gain'][name]+=np.sum((value[:,:,0]-base[:,:,0])*weights[:,None],axis=0)*100
                item['repairs'][name]+=np.stack([np.sum(failure&(value[:,:,0]>=.7),axis=0),np.sum(failure&(value[:,:,0]>.9),axis=0)],-1)
                events=np.stack([value[:,:,1]<1,value[:,:,2]<1,value[:,:,0]==0],-1)
                item['safety'][name]+=np.sum((events.astype(float)-old_events.astype(float))*weights[:,None,None],axis=0)
        sources.append(dict(response=info['path'],matrix=response['matrix'],matrix_sha256=response['matrix_sha256']))
        if number%50==0:atomic(ROOT/'analysis/frozen_privileged_repair_envelope/LIVE.json',dict(time=stamp(),source_number=number,total_sources=len(review['sources']),completed_policy_keys=len(acc)))
    assert set(acc)==set(complete)
    result=[]
    for key,item in sorted(acc.items()):
        assert item['folds']==set(range(5))
        assert np.allclose(item['gain']['actual'],complete[key]['standardized_pdms_gain_by_noise'],rtol=0,atol=1e-10)
        assert np.all(item['gain']['beneficial_only']>=-1e-10)
        result.append(dict(method=key[0],system=key[1],policy=key[2],
            standardized_gain_by_noise={k:v.tolist() for k,v in item['gain'].items()},
            failure_repair70_repair90_counts_by_noise={k:v.tolist() for k,v in item['repairs'].items()},
            standardized_net_NC_DAC_zero_rates_by_noise={k:v.tolist() for k,v in item['safety'].items()}))
    target=ROOT/'analysis/frozen_privileged_repair_envelope/SUMMARY.json';assert not target.exists()
    atomic(target,dict(status='COMPLETE_FROZEN_EXISTING_POLICY_PRIVILEGED_ENVELOPES',time=stamp(),snapshot=pointer,
        recipes=result,complete_fivefold_policies=len(result),sources=sources,
        identity_always_allowed_for_beneficial_envelope=True,
        S0_fixed_branch_scope='Fix Base versus this policy after observing S0; the policy itself may choose different experts/amounts on later noises. This is not a scene-fixed expert Oracle.',
        scope='Class-standardized exploration panels. Each envelope contains Base plus one fixed policy output; not a union of all4549 policies, not own-K expert Oracle or theoretical optimum. Full natural own-K expert/matched-Base diagnostics remain separate.',
        all_original_actual_gains_reproduced_to_1e10=True,new_models=0,new_rollouts=0,new_scores=0,
        validation_accessed=False,test_accessed=False,confirmation_pack_unchanged=True,source_sha256=sha(Path(__file__))))
    print(json.dumps(dict(status='COMPLETE',path=str(target.relative_to(ROOT)),policies=len(result),new_rollouts=0,new_scores=0)),flush=True)


if __name__=='__main__':main()
