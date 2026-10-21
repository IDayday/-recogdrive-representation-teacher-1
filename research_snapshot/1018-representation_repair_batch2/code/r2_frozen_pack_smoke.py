"""Universal evaluation versus the frozen single-method evaluators, exact replay."""
from r2_common import *


def run(engine,task,pool):
    from r2_frozen_policy_pack import run as evaluate
    from r2_hard_policy_eval import run as hard
    from r2_candidate_eval import run as candidate
    from r2_behavior_router_eval import run as joint
    result=evaluate(engine,task['evaluation'],pool);records=read(ROOT/result['path'])['records'];pack=read(ROOT/task['evaluation']['pack']);reference={(r['arm'],r['token'],r['seed_index']):r for r in records};comparisons=[]
    for kind,handler in [('hard',hard),('candidate',candidate),('joint',joint)]:
        selected=[c for c in pack['policies'] if c['kind']==kind];policies=[]
        for c in selected:
            policy=read(ROOT/c['policy'])
            if kind=='joint':policies.append(dict(policy['configuration'],id=c['id']))
            else:policies.append(dict(id=c['id'],policy=c['policy'],policy_sha256=c['policy_sha256']))
        point=ROOT/task['stage']/'points'/(kind+'.json')
        atomic(point,dict(id=task['id']+'_'+kind,mode='engineering',heldout_fold=-1,policies=policies,panel=task['evaluation']['panel'],seeds=task['evaluation']['seeds']))
        evaluated=handler(engine,dict(id=task['id']+'_'+kind,stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=len(task['evaluation']['panel'])),pool)
        checked=0
        for r in read(ROOT/evaluated['path'])['records']:
            key=(r['arm'],r['token'],r['seed_index'])
            if key not in reference:continue
            old=reference[key];assert r['trajectory']==old['trajectory'] and r['score']==old['score'],(kind,key)
            if 'choice' in r:assert r['choice']==old['choice']
            checked+=1
        assert checked>=len(task['evaluation']['panel'])*len(task['evaluation']['seeds'])*(1+len(selected))
        comparisons.append(dict(kind=kind,records_exact=checked,original_evaluator=evaluated['path']))
    path=ROOT/'provenance/FROZEN_POLICY_PACK_ENGINEERING_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),actual_pack=result,comparisons=comparisons,
        token_full_uniform_and_pre_context_actual_scored=True,raw_expert_outcomes_available=True,
        Base_trajectory_and_score_exact=True,all_heldout_folds_minus_one=True,validation_accessed=False,test_accessed=False,
        scope='Engineering-only pack from preexisting training/pilot artifacts. It is not the final selection or final confirmation.'))
    return dict(path=str(path.relative_to(ROOT)),comparisons=comparisons)
