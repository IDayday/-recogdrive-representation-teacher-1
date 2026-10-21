"""Exact threshold variants share an actual trajectory and independent score.

The frozen evaluator still performs every physical rollout. A threshold changes
only whether to keep that trajectory or exact Base. No prediction of PDMS, linear
mixture of outcomes, or approximate trajectory is used to expand the records.
"""
from r2_common import *


def run(engine,task,pool):
    from r2_library_rollouts import block
    point=read(ROOT/task['point']);policies=point['policies']
    interfaces=all(block(part) in ['interface_pre','interface_post'] for p in policies for part in p['model']['parts'])
    if interfaces:
        from r2_behavior_router_eval import run as original
    else:
        from r2_behavior_router_raw_eval_v1 import run as original
    if point['mode']!='training' or len(policies)!=12 or any(p.get('force_Base',False) for p in policies):return original(engine,task,pool)
    groups={}
    def key(p):return digest(dict(model=p['model']['task']['id'],checkpoint=p['checkpoint'],multiplier=p.get('multiplier',1.)))
    for p in policies:groups.setdefault(key(p),[]).append(p)
    if len(groups)!=4 or any(max(p.get('identity_threshold',1.01) for p in group)<1. for group in groups.values()):return original(engine,task,pool)
    selected={k:max(group,key=lambda p:p.get('identity_threshold',1.01)) for k,group in groups.items()}
    private=ROOT/'runs/joint_threshold_reuse_v2';source_point=private/'points'/(digest(dict(point=task['point']))[:24]+'.json')
    reduced=dict(point,policies=list(selected.values()),runtime_only_threshold_reuse=True,original_point=task['point'])
    # Identical descriptors can be prepared concurrently by different chunks.
    if source_point.exists():assert digest(read(source_point))==digest(reduced)
    else:atomic(source_point,reduced)
    source_task=dict(task,id='memo_'+task['id'],stage=str(private.relative_to(ROOT)),point=str(source_point.relative_to(ROOT)))
    result=original(engine,source_task,pool);actual=read(ROOT/result['path']);baseline={};lookup={}
    for r in actual['records']:
        if r['arm']=='baseline':baseline[(r['token'],r['seed_index'])]=r
        else:lookup[(r['arm'],r['token'],r['seed_index'])]=r
    expanded=[dict(r) for r in actual['records'] if r['arm']=='baseline']
    for policy in policies:
        source=selected[key(policy)]
        for token,noise in baseline:
            record=dict(lookup[(source['id'],token,noise)])
            abstain=bool(record['identity_weight']>=policy.get('identity_threshold',1.01))
            hard_identity=record['kind']=='hard_continuous' and record['selected_expert']==0
            if abstain or hard_identity:
                record.update(trajectory=baseline[(token,noise)]['trajectory'],score=baseline[(token,noise)]['score'],quality=baseline[(token,noise)]['quality'],statistics=[])
            record.update(arm=policy['id'],abstained=abstain);expanded.append(record)
    path=ROOT/task['stage']/'results'/(task['id']+'.json');assert not path.exists()
    atomic(path,dict(actual,task=task,records=expanded,runtime_version='joint_threshold_reuse_v2',physical_policies=len(selected),logical_policies=len(policies),
        physical_rollout_source=result['path'],physical_rollout_sha256=result['sha256'],actual_scored_outcomes_reused=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(expanded),seconds=actual['seconds'],physical_policies=len(selected),logical_policies=len(policies))
