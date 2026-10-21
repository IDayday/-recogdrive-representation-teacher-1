"""Freeze the complete exploration snapshot and prespecified confirmation pack.

Uses only exploration CV and fitted all-data artifacts. Missing or ambiguous
deployment artifacts are errors, never a reason to silently rerank a family.
"""
from r2_common import *
from collections import defaultdict
import re


def main():
    setup('freeze_confirmation_candidates')
    protocol_path=ROOT/'config/FINAL_CONFIRMATION_SELECTION_PROTOCOL_V1.json'
    protocol=read(protocol_path)
    destination=ROOT/'provenance/final_confirmation'
    assert not (destination/'SELECTION.json').exists()
    snapshot=read(ROOT/'analysis/extended_cv_reviews/LATEST.json')
    assert sha(ROOT/snapshot['path'])==snapshot['sha256']
    review=read(ROOT/snapshot['path']);index={}
    for row in review['recipes']:
        if row['complete_five_folds']:
            index.setdefault((row['system'],row['method']),set()).add(row['policy'])
    expected={'warm_hard':6,'candidate_selector':4,
        'additional_joint_hard_continuous':6,'additional_joint_soft_joint':6}
    spatial=read(ROOT/'config/SELECTED_SPATIAL_FINAL_FRONTIER_PROTOCOL_V1.json')
    for stem in spatial['systems_stems']:
        assert (ROOT/'analysis/selected_spatial_final_replication'/(stem+'_THREE_FITS_READY.json')).exists()
        for fit in range(3):
            assert all(len(index.get((f'{stem}_seed{fit}',m),set()))==n for m,n in expected.items())
    groups=defaultdict(dict)
    for row in review['recipes']:
        match=re.fullmatch(r'(.+_K[2-8])_seed([0-2])',row['system'])
        if match and row['complete_five_folds']:
            key=(match[1],row['method'],row['policy']);fit=int(match[2])
            assert fit not in groups[key];groups[key][fit]=row
    complete=[]
    for key,fits in sorted(groups.items()):
        if sorted(fits)!=[0,1,2]:continue
        gains=[fits[i]['standardized_pdms_gain'] for i in range(3)]
        safety=[fits[i]['approximate_safety_all_noise'] for i in range(3)]
        noise=[fits[i]['standardized_pdms_gain_by_noise'] for i in range(3)]
        complete.append(dict(key=list(key),fit_mean_gains=gains,fit_noise_gains=noise,
            fit_safety=safety,mean=sum(gains)/3,minimum_fit_mean=min(gains),
            allfit_safety=all(safety),nonidentity=any(abs(g)>1e-10 for g in gains),
            stable_positive_safe=all(safety) and all(g>0 for values in noise for g in values)))
    nonzero=[r for r in complete if r['nonidentity']];assert nonzero
    safe=[r for r in nonzero if r['allfit_safety']]
    assert safe, 'No nonzero protected-event-compatible family: record Base fallback and explicitly resolve diagnostic selection.'
    topmean=lambda rows:sorted(rows,key=lambda v:(-v['mean'],v['key']))[0]
    selected=[('Safety',topmean(safe)),('PDMS',topmean(nonzero)),
        ('PDMS_robust_fit_control',sorted(nonzero,key=lambda v:(-v['minimum_fit_mean'],-v['mean'],v['key']))[0])]
    catalog_pointer=read(ROOT/'analysis/all_data_policy_catalog/LATEST.json')
    assert sha(ROOT/catalog_pointer['path'])==catalog_pointer['sha256']
    catalog=read(ROOT/catalog_pointer['path']);lookup=defaultdict(list)
    for entry in catalog['entries']:
        lookup[(entry['system'],entry['method'],entry['policy'])].append(entry)
    family_path=destination/'THREE_FIT_FAMILY.json'
    atomic(family_path,dict(time=stamp(),snapshot=snapshot,recipes=complete,
        stable_positive_safe_families=sum(r['stable_positive_safe'] for r in complete)))
    pack=dict(policies=[dict(id='Base',kind='Base')],include_raw_experts=True,
        base_resampling_extra_candidates=0)
    bindings=[];seen={}
    for role,chosen in selected:
        stem,method,policy_id=chosen['key'];structure=digest(chosen['key'])[:20]
        for fit in range(3):
            key=(f'{stem}_seed{fit}',method,policy_id)
            matches=lookup[key]
            if matches and matches[0]['kind']=='finite':
                matches=[m for m in matches if read(ROOT/m['training'])['task'].get('science_phase')=='formal']
            assert len(matches)==1,('Missing/ambiguous selected all-data policy',key,len(matches))
            entry=matches[0];kind=entry['kind']
            if kind=='finite':
                assert sha(ROOT/entry['training'])==entry['training_sha256']
                model=read(ROOT/entry['training']);checkpoint=entry['checkpoint']
                assert model['heldout_fold']==-1 and sha(ROOT/checkpoint['path'])==checkpoint['sha256']
                target=destination/'finite_policies'/(structure+f'_fit{fit}.json')
                if not target.exists():
                    atomic(target,dict(status='FROZEN_EXISTING_FORMAL_ALL_DATA_FINITE_POLICY',
                        system=model['system'],heldout_fold=-1,role=model['role'],tier=model['tier'],
                        configuration=dict(model=model,checkpoint=checkpoint),
                        training=entry['training'],training_sha256=entry['training_sha256']))
                artifact=str(target.relative_to(ROOT));hashed=sha(target)
            else:
                artifact=entry['artifact'];hashed=entry['sha256'];assert sha(ROOT/artifact)==hashed
            actual=read(ROOT/artifact)
            parts=actual['configuration']['model']['parts'] if kind in ['joint','finite'] else actual['parts']
            assert actual['heldout_fold']==-1
            pack['base_resampling_extra_candidates']=max(pack['base_resampling_extra_candidates'],len(parts))
            identity=(structure,fit)
            if identity not in seen:
                ident=role+'_fit'+str(fit);seen[identity]=ident
                pack['policies'].append(dict(id=ident,kind=kind,policy=artifact,policy_sha256=hashed,
                    structure_id=structure,selection_role=role,fit_replicate=fit,
                    selection_roles=[role]))
            else:
                ident=seen[identity]
                next(c for c in pack['policies'] if c['id']==ident)['selection_roles'].append(role)
            bindings.append(dict(role=role,fit=fit,pack_policy=ident,source_cv_key=list(key),
                artifact=artifact,sha256=hashed,nominal_K=len(parts)))
    atomic(destination/'EXPLORATION_SNAPSHOT.json',snapshot)
    atomic(destination/'PACK.json',pack)
    selection=dict(status='FROZEN_BEFORE_NATURAL_CONFIRMATION',time=stamp(),
        protocol=str(protocol_path.relative_to(ROOT)),protocol_sha256=sha(protocol_path),
        snapshot=snapshot,all_three_fit_family=str(family_path.relative_to(ROOT)),
        all_three_fit_family_sha256=sha(family_path),selected_families=[dict(role=r,**v) for r,v in selected],
        bindings=bindings,pack='provenance/final_confirmation/PACK.json',
        pack_sha256=sha(destination/'PACK.json'),catalog=catalog_pointer,
        stable_positive_safe_families=sum(r['stable_positive_safe'] for r in complete),
        Base_is_official_fallback_without_stable_qualified_gain=True,
        diagnostic_nonzero_families_do_not_establish_stable_improvement=True,
        final_test_policy_family_frozen=True,validation_accessed=False,test_accessed=False)
    atomic(destination/'SELECTION.json',selection)
    print(json.dumps(dict(status=selection['status'],selected=selection['selected_families'],
        pack_policies=len(pack['policies']),stable_positive_safe=selection['stable_positive_safe_families'])),flush=True)


if __name__=='__main__':main()
