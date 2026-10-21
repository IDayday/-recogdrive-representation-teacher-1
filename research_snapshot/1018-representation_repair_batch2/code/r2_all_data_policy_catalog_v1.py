"""Read-only deployment-artifact catalog; no ranking or confirmation access."""
from r2_common import *


def main():
    setup('all_data_policy_catalog')
    entries=[]
    locations=[('routers','hard','warm_hard'),
               ('candidate_selectors','candidate','candidate_selector'),
               ('joint_policies','joint','joint'),
               ('additional_joint_policies','joint','additional_joint')]
    counts={}
    for folder,kind,method in locations:
        count=0
        for path in sorted((ROOT/folder).glob('*/POLICY.json')):
            policy=read(path)
            if policy.get('heldout_fold')!=-1:continue
            actual_method=method+'_'+policy['kind'] if kind=='joint' else method
            entries.append(dict(system=policy['system'],method=actual_method,
                policy=policy['role']+'_'+policy['tier'],kind=kind,
                artifact=str(path.relative_to(ROOT)),sha256=sha(path)))
            count+=1
        counts[folder]=count
    finite_count=0
    for path in sorted((ROOT/'finite_outcome_routers').glob('*/TRAINING.json')):
        model=read(path)
        if model.get('heldout_fold')!=-1:continue
        for checkpoint in model['checkpoints']:
            if checkpoint['step']==128 and model['method']!='ce_continuation':continue
            entries.append(dict(system=model['system'],method='finite_outcome_router_finite_outcome',
                policy=model['method']+'_'+str(checkpoint['step'])+'_'+model['role']+'_'+model['tier'],
                kind='finite',training=str(path.relative_to(ROOT)),training_sha256=sha(path),
                checkpoint=checkpoint))
            finite_count+=1
    counts['finite_outcome_routers_checkpoints']=finite_count
    from collections import Counter
    keys=Counter((v['system'],v['method'],v['policy']) for v in entries)
    ambiguous=[dict(system=k[0],method=k[1],policy=k[2],artifacts=n)
               for k,n in keys.items() if n>1]
    folder=ROOT/'analysis/all_data_policy_catalog'/stamp().replace(':','')
    target=folder/'CATALOG.json'
    atomic(target,dict(status='ALL_DATA_ARTIFACT_CATALOG_NOT_SELECTION',time=stamp(),
        entries=entries,counts=counts,ambiguous_keys=ambiguous,
        ambiguity_rule='Retain every artifact; selection must bind to original CV producer provenance, never first directory match.',
        source_sha256=sha(Path(__file__)),
        validation_accessed=False,test_accessed=False,no_model_or_resource_actions=True))
    pointer=dict(time=stamp(),path=str(target.relative_to(ROOT)),sha256=sha(target),counts=counts,ambiguous_keys=len(ambiguous))
    atomic(ROOT/'analysis/all_data_policy_catalog/LATEST.json',pointer)
    print(json.dumps(pointer),flush=True)


if __name__=='__main__':main()
