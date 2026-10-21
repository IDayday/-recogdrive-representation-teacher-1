"""Read-only paired audit of completed mechanistic pilots and five-fold banks.

This does not select final policies, fit parameters, or access natural validation.
Stored outcomes are reused; repeated noise remains within each scene.
"""
from r2_common import *
import re


def assess(path):
    import numpy as np
    d=read(path)
    assert d['heldout_fold']==0 and not d['validation_accessed'] and not d['test_accessed']
    assert sha(ROOT/d['matrix'])==d['matrix_sha256'] and sha(ROOT/d['policy'])==d['policy_sha256']
    with np.load(ROOT/d['matrix']) as z:
        data={k:np.array(z[k]) for k in ['global_indices','seeds','base_scores','selected_scores','choice','weights']}
    ii=data['global_indices'];nn=data['seeds'];base=data['base_scores'];after=data['selected_scores'];w=data['weights']
    assert len(ii)==3*len(set(ii.tolist())) and set(nn.tolist())=={0,1,2}
    assert len(set(zip(ii.tolist(),nn.tolist())))==len(ii) and np.isfinite(after).all()
    np.testing.assert_allclose(w.sum(),1.,rtol=0,atol=1e-12)
    gain=float(w@(after[:,0]-base[:,0])*100)
    np.testing.assert_allclose(gain,d['metrics']['weighted_pdms_gain'],rtol=0,atol=1e-10)
    by_noise=[]
    for n in range(3):
        keep=nn==n;wn=w[keep]/w[keep].sum();by_noise.append(float(wn@(after[keep,0]-base[keep,0])*100))
    metrics=dict(d['metrics'],gain_by_noise=by_noise,identity_outputs=int(np.sum(data['choice']==0)),examples=len(ii))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),system=d['system'],role=d['role'],view=d['context_view'],fit_seed=d['fit_seed'],metrics=metrics,matrix_sha256=d['matrix_sha256']),data


def paired(a,b,by):
    import numpy as np
    ma,da=a;mb,db=b
    for k in ['global_indices','seeds','base_scores','weights']:
        assert np.array_equal(da[k],db[k]),(by,k)
    difference=float(da['weights']@(db['selected_scores'][:,0]-da['selected_scores'][:,0])*100)
    np.testing.assert_allclose(difference,mb['metrics']['weighted_pdms_gain']-ma['metrics']['weighted_pdms_gain'],atol=1e-10,rtol=0)
    return dict(comparison=by,reference=ma['path'],variant=mb['path'],variant_minus_reference_gain=difference,
        variant_minus_reference_gain_by_noise=[y-x for x,y in zip(ma['metrics']['gain_by_noise'],mb['metrics']['gain_by_noise'])],
        net_event_difference={k:mb['metrics'][k]-ma['metrics'][k] for k in ['net_collision','net_offroad','net_zero','net_TTC','net_failures']},
        changed_choices=int(np.sum(da['choice']!=db['choice'])),same_complete_case_seed_Base_weight_panel=True)


def main():
    setup('auxiliary_panel_review')
    import numpy as np
    folder=ROOT/'analysis/auxiliary_completed_panels'/stamp().replace(':','').replace('+','_');folder.mkdir(parents=True,exist_ok=False)
    panels={};large={};state={}
    for view in ['post_valid','pre_all','post_valid_state','post_valid_zero']:
        for path in (ROOT/'analysis/context_token_policy_cv'/view).glob('*.json'):
            d=read(path)
            if '__largeH_' not in d.get('system','') and '__stateH_' not in d.get('system',''):continue
            item,data=assess(path);panels[item['path']]=(item,data)
            lm=re.fullmatch(r'representation_K2_seed0__largeH_(frozen8k|(?:original|augmented)_total(?:16000|32000))_(post_valid|pre_all)_fit(202610180[123])',item['system'])
            sm=re.fullmatch(r'representation_K2_seed0__stateH_(original|augmented)_total(16000|32000)_(post_valid_state|post_valid_zero)_fit2026101801',item['system'])
            if lm:large[(lm[1],lm[2],int(lm[3]),item['role'])]=(item,data)
            elif sm:state[(sm[1],int(sm[2]),sm[3],item['role'])]=(item,data)
    assert len(large)==52 and len(state)==16,(len(large),len(state))
    pairs=[]
    for (tag,view,fit,role),a in sorted(large.items()):
        if tag.startswith('original_'):
            key=(tag.replace('original_','augmented_',1),view,fit,role)
            pairs.append(paired(a,large[key],'distinct_success_data_at_matched_updates_and_class_sampling'))
        if tag.endswith('16000'):
            key=(tag.replace('16000','32000'),view,fit,role)
            pairs.append(paired(a,large[key],'additional_continuation_updates_same_data_seed_warm'))
    for (arm,steps,view,role),a in sorted(state.items()):
        if view=='post_valid_zero':pairs.append(paired(a,state[(arm,steps,'post_valid_state',role)],'actual_ego_history_vs_equal_size_zero_tokens'))
    ens=[]
    for path in sorted((ROOT/'analysis/critic_ensembles').glob('outcome_available_critic_ensemble_*/SUMMARY.json')):
        d=read(path);assert d['new_model_or_trajectory_or_scoring_runs']==0
        assert d['zero_identity_and_single_member_rule_checked'] and len(d['outputs'])==3
        for out in d['outputs']:
            response=read(ROOT/out['path']);p=read(ROOT/out['policy']);assert sha(ROOT/out['policy'])==response['policy_sha256']
            assert p['heldout_fold']==0 and len(p['members'])==3 and p['zero_expert_exact'] and p['no_hidden_or_trajectory_linear_mix']
            assert sha(ROOT/response['matrix'])==response['matrix_sha256']
            with np.load(ROOT/response['matrix']) as z:
                ids=np.array(z['global_indices']);s=np.array(z['scores']);seeds=np.array(z['seeds'])
            assert list(seeds)==[0,1,2] and s.shape==(len(ids),2,3,7) and np.isfinite(s).all()
            # Every ensemble uses the exact same held bank as the matched single
            # readout pilots. Reuse that checked class-standardization weight.
            target=next(v for v in large.values() if v[0]['system']==p['system']+'_fit2026101801' and v[0]['role']==p['role'])
            _,dat=target;lookup={(int(i),int(n)):j for j,(i,n) in enumerate(zip(dat['global_indices'],dat['seeds']))}
            weight=np.array([[dat['weights'][lookup[(int(i),n)]] for n in range(3)] for i in ids])
            reference=np.array([[dat['base_scores'][lookup[(int(i),n)]] for n in range(3)] for i in ids]);assert np.array_equal(reference,s[:,0])
            delta=s[:,1,:,0]-s[:,0,:,0];gain_by_noise=(weight*delta).sum(0)/weight.sum(0)*100
            events={}
            for label,col in [('collision',1),('offroad',2),('zero',0),('TTC',3),('failure',-1)]:
                a=s[:,1];b=s[:,0]
                aa=a[:,:,0]<.7 if col==-1 else a[:,:,0]==0 if label=='zero' else a[:,:,col]<1
                bb=b[:,:,0]<.7 if col==-1 else b[:,:,0]==0 if label=='zero' else b[:,:,col]<1
                events[label]=(aa.astype(int)-bb.astype(int)).sum(0).tolist()
            ens.append(dict(system=p['system'],role=p['role'],method=out['method'],gain_by_noise=gain_by_noise.tolist(),mean_gain=float(gain_by_noise.mean()),sample_net_events_by_noise=events,policy=out['policy'],source=out['path'],setting=p['setting']))
    assert len(ens)==48,len(ens)
    potential=[]
    for path in sorted((ROOT/'analysis/held_fivefold_potential').glob('*/SUMMARY.json')):
        d=read(path);assert d['folds']==list(range(5)) and d['same_policy_K_parts_never_other_roles_union']
        for spec in d['task']['inputs']:
            for key in ['potential','stability']:assert sha(ROOT/spec[key])==spec[key+'_sha256']
        roles={}
        for role,value in d['roles'].items():
            assert len(set(value['nonzero_modules_by_fold']))==1
            roles[role]={k:v for k,v in value.items() if k not in ['sources','unconditional_each_candidate_by_fold']}
        potential.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),system=d['system'],sampled_cases=d['sampled_cases'],roles=roles))
    latest=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');assert sha(ROOT/latest['path'])==latest['sha256'];cv=read(ROOT/latest['path']);joint=[a for a in cv['recipes'] if a['complete_five_folds'] and a['method'].startswith('joint_')]
    assert joint
    summary=dict(status='COMPLETED_MECHANISTIC_PILOTS_AUDITED',time=stamp(),large_success_policies=[v[0] for v in large.values()],state_policies=[v[0] for v in state.values()],paired_comparisons=pairs,ensemble_policies=ens,fivefold_bank_potential=potential,first_complete_true_joint_recipes=joint,cv_snapshot=latest,
        scope='One held session fold for all auxiliary pilots; shared expert bank and warm initialization. Three continuation RNGs do not replace independent whole-system fits. Candidate fitting class proportions held fixed; natural candidate-prior fitting has not been tested here.',
        no_new_model_trajectory_or_scoring=True,validation_accessed=False,test_accessed=False)
    atomic(folder/'SUMMARY.json',summary)
    atomic(ROOT/'provenance/AUXILIARY_COMPLETED_PANELS_ACCEPTANCE.json',dict(status='PASS',time=stamp(),path=str((folder/'SUMMARY.json').relative_to(ROOT)),sha256=sha(folder/'SUMMARY.json'),large_policies=52,state_policies=16,ensemble_policies=48,paired_comparisons=len(pairs),full_fivefold_bank_summaries=len(potential),complete_joint_recipes=len(joint),all_matrix_policy_hashes_and_paired_panels_checked=True))
    def compact(items,metric):
        values=[metric(v) for v in items];return dict(n=len(values),positive=sum(v>1e-12 for v in values),zero=sum(abs(v)<=1e-12 for v in values),minimum=min(values),maximum=max(values))
    print(json.dumps(dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),large=compact([v[0] for v in large.values()],lambda v:v['metrics']['weighted_pdms_gain']),state=compact([v[0] for v in state.values()],lambda v:v['metrics']['weighted_pdms_gain']),ensemble=compact(ens,lambda v:v['mean_gain']),joint=compact(joint,lambda v:v['standardized_pdms_gain']),fivefold_banks=len(potential)),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
