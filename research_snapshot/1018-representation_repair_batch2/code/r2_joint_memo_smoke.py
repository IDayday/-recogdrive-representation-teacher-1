"""Exact A/B of all logical trajectories, scores and gates, both execution paths."""
from r2_common import *


def run(engine,task,pool):
    from r2_behavior_router_eval import run as cached
    from r2_behavior_router_raw_eval_v1 import run as raw
    from r2_joint_eval_memo_v2 import run as optimized
    report=[]
    for number,test in enumerate(task['tests']):
        model=read(ROOT/test['training_path']);policies=[]
        if test.get('prepare_two_checkpoints'):
            from r2_behavior_router_raw_locations_v1 import run as train
            spec=dict(model['task'],id='memo_raw_two_checkpoints_'+model['kind'],steps=12,checkpoints=[6,12],warmup_steps=0)
            trained=train(engine,spec,pool);model=read(ROOT/trained['path'])
        for ck in model['checkpoints'][-2:]:
            for multiplier in [.5,1.]:
                for threshold in [.5,.9,1.01]:
                    spec=dict(checkpoint=ck,multiplier=multiplier,identity_threshold=threshold)
                    policies.append(dict(id='memo_ab_'+digest(spec)[:24],model=model,**spec))
        # Eight-step engineering models have only one checkpoint; duplicate it
        # with a different path is not a real additional physical configuration.
        # Select actual distinct preexisting checkpoints in the producer instead.
        assert len(policies)==12
        panel=task['panel'];point=ROOT/task['stage']/'points'/('case'+str(number)+'.json');atomic(point,dict(id='memo_ab_case'+str(number),mode='training',policies=policies,panel=panel,seeds=[0,1,2]))
        original=raw if test['raw'] else cached
        before=original(engine,dict(id='memo_reference_'+str(number),stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=len(panel)),pool)
        after=optimized(engine,dict(id='memo_optimized_'+str(number),stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=len(panel)),pool)
        old=read(ROOT/before['path']);new=read(ROOT/after['path']);a={(r['arm'],r['token'],r['seed_index']):r for r in old['records']};b={(r['arm'],r['token'],r['seed_index']):r for r in new['records']};assert a.keys()==b.keys()
        for k in a:assert digest(a[k])==digest(b[k]),('Trajectory/score/routing annotation changed',number,k)
        assert new['physical_policies']==4 and new['logical_policies']==12
        report.append(dict(raw=test['raw'],kind=model['kind'],records_exact=len(a),reference_seconds=old['seconds'],optimized_seconds=new['seconds'],original=before['path'],optimized=after['path']))
    path=ROOT/'provenance/JOINT_THRESHOLD_REUSE_ENGINEERING_PASS.json';atomic(path,dict(status='PASS',time=stamp(),all_record_fields_exact=True,comparisons=report,
        no_changed_seed_or_trajectory_or_scoring=True,only_repeated_thresholds_collapsed=True,scope='Same-worker short A/B on frozen training panels, not a whole-job speed claim.'))
    return dict(path=str(path.relative_to(ROOT)),comparisons=report)
