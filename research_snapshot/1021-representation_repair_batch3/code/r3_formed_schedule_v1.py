"""Metadata-only full-coverage batches, preserving independent fitted identities.

Policies with shared raw expert dependencies are grouped together. This is a
draft work decomposition, not an outcome-based admission or a GPU submission.
"""
from r3_common import *
from collections import Counter,defaultdict
import argparse


def main(a):
    from r3_formed_catalog_v3 import part_key
    catalog_path=ROOT/'manifests/FORMED_CATALOG_DRAFT_V3.json';catalog=read(catalog_path)
    entries=catalog['entries'];by_id={e['id']:e for e in entries};raw={};dependencies={};groups=defaultdict(list)
    for e in entries:
        if e['kind'] in ['batch2_learned','batch2_delta','batch2_analytic']:
            key=digest(part_key(e['definition']));assert key not in raw;raw[key]=e['id']
    for e in entries:
        if not e['kind'].startswith('batch2_policy_'):continue
        definition=e['definition'];path=BATCH2/definition['policy_path'];assert sha(path)==definition['policy_sha256']
        policy=read(path);kind=e['kind'].removeprefix('batch2_policy_')
        parts=policy['configuration']['model']['parts'] if kind in ['joint','finite'] else policy['parts']
        keys=[digest(part_key(p)) for p in parts];assert all(k in raw for k in keys)
        deps=sorted({raw[k] for k in keys});dependencies[e['id']]=deps;groups[tuple(deps)].append(e['id'])
    draft=[]
    for deps,ids in sorted(groups.items()):
        current=[];joint=0
        for ident in sorted(ids,key=lambda i:(by_id[i]['kind'],i)):
            is_joint=by_id[ident]['kind']=='batch2_policy_joint'
            if current and (len(current)>=a.max_policies or joint+is_joint>a.max_joint):
                draft.append(dict(policies=current,dependencies=list(deps)));current=[];joint=0
            current.append(ident);joint+=is_joint
        if current:draft.append(dict(policies=current,dependencies=list(deps)))
    # Merge small bundles when their union still fits the bounded raw branch
    # budget. Only scheduling changes; every policy retains its ordered parts.
    packs=[]
    for item in sorted(draft,key=lambda d:(-len(d['dependencies']),-len(d['policies']),d['policies'])):
        own=set(item['dependencies']);joint=sum(by_id[i]['kind']=='batch2_policy_joint' for i in item['policies'])
        eligible=[p for p in packs if len(set(p['dependencies'])|own)<=a.max_raw and len(p['policies'])+len(item['policies'])<=a.max_policies and p['joint_count']+joint<=a.max_joint]
        if eligible:
            target=max(eligible,key=lambda p:(len(set(p['dependencies'])&own),-len(p['dependencies'])))
            target['dependencies']=sorted(set(target['dependencies'])|own);target['policies']+=item['policies'];target['joint_count']+=joint
        else:packs.append(dict(dependencies=sorted(own),policies=item['policies'][:],joint_count=joint,independent_entries=[]))
    assigned=set()
    for pack in packs:
        pack['independent_entries']=[i for i in pack['dependencies'] if i not in assigned]
        assigned.update(pack['independent_entries'])
    leftover=[e['id'] for e in entries if not e['kind'].startswith('batch2_policy_') and e['id'] not in assigned]
    for start in range(0,len(leftover),a.max_raw):
        own=leftover[start:start+a.max_raw]
        deps=[i for i in own if by_id[i]['kind'] in ['batch2_learned','batch2_delta','batch2_analytic']]
        packs.append(dict(dependencies=deps,policies=[],joint_count=0,independent_entries=own));assigned.update(own)
    formal=[]
    for p in packs:
        ordered=sorted(p['independent_entries'])+sorted(p['policies']);assert len(ordered)==len(set(ordered))
        actual_raw=set(p['dependencies'])|set(p['independent_entries'])
        raw_kinds=Counter(by_id[i]['kind'] for i in actual_raw)
        spec=dict(entries=ordered,dependencies=sorted(p['dependencies']),catalog_sha256=sha(catalog_path))
        ident='formed_pack_'+digest(spec)[:24]
        formal.append(dict(id=ident,**spec,counts=dict(Counter(by_id[i]['kind'] for i in ordered)),
                           raw_dependency_count=len(p['dependencies']),joint_count=p['joint_count'],
                           unique_forward_branches_upper_per_scene=5*(1+len(actual_raw)+p['joint_count']),
                           raw_kinds=dict(raw_kinds),full_navtrain_required=True,full_frozen_navtest_required=True))
    covered=[i for p in formal for i in p['entries']]
    assert Counter(covered)==Counter(by_id.keys()),'Every formed identity must appear exactly once'
    result=dict(status='DRAFT_FULL_COVERAGE_SCHEDULE_NOT_RUNTIME_ADMITTED',time=stamp(),
                catalog=str(catalog_path.relative_to(ROOT)),catalog_sha256=sha(catalog_path),
                packs=formal,entries=len(entries),pack_count=len(formal),limits=dict(max_raw=a.max_raw,max_joint=a.max_joint,max_policies=a.max_policies),
                actual_scientific_population='103288 navtrain, 12146 frozen navtest, S0-S4',
                first42_snapshot_required_before_execution=True,outcome_based_screening=False,
                distinct_independent_fit_ids_preserved=True,test_results_not_used_for_grouping=True,
                maximum_sum_forward_branches_per_scene=sum(p['unique_forward_branches_upper_per_scene'] for p in formal))
    path=ROOT/'manifests/FORMED_SCHEDULE_DRAFT_V1.json';assert not path.exists();atomic(path,result)
    print(json.dumps({k:v for k,v in result.items() if k!='packs'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-raw',type=int,default=32);p.add_argument('--max-joint',type=int,default=8);p.add_argument('--max-policies',type=int,default=128);main(p.parse_args())
