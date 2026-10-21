"""Bitwise training A/B before adopting any immutable Base-output cache."""
from r2_common import *


def equal_arrays(a,b):
    import numpy as np
    assert len(a['checkpoints'])==len(b['checkpoints']);reports=[]
    for old,new in zip(a['checkpoints'],b['checkpoints']):
        assert old['step']==new['step']
        with np.load(ROOT/old['path']) as x,np.load(ROOT/new['path']) as y:
            assert x.files==y.files;difference={k:float(np.max(np.abs(x[k]-y[k]))) for k in x.files}
            assert all(np.array_equal(x[k],y[k]) for k in x.files),difference
        reports.append(dict(step=old['step'],all_arrays_bitwise_equal=True,max_abs_difference=difference))
    return reports


def run(engine,task,pool):
    from r2_learned_expert_v3 import run as original_expert
    from r2_learned_expert_v4_nativecache import run as cached_expert
    from r2_behavior_router import run as original_joint
    from r2_behavior_router_v2_nativecache import run as cached_joint
    assert read(ROOT/'provenance/NATIVE_CACHE_CONTRACT_PASS.json')['status']=='PASS'
    sources=[('expert',read(ROOT/'runs/cached_training_ab_v3/tasks.json')[0],original_expert,cached_expert)]
    for kind in ['hard_continuous','soft_joint']:
        old=read(ROOT/'behavior_routers'/('joint_router_smoke_'+kind)/'TRAINING.json')['task'];sources.append((kind,old,original_joint,cached_joint))
    comparisons=[]
    for name,configuration,baseline,optimized in sources:
        reference=baseline(engine,dict(configuration,id='native_ab_reference_'+name),pool)
        first=optimized(engine,dict(configuration,id='native_ab_first_'+name),pool)
        before=dict(engine.immutable_native_counts);hot=optimized(engine,dict(configuration,id='native_ab_hot_'+name),pool);after=dict(engine.immutable_native_counts)
        assert after['hits']-before['hits']==configuration['steps']
        a=read(ROOT/reference['path']);b=read(ROOT/first['path']);c=read(ROOT/hot['path'])
        reports=equal_arrays(a,b);hot_reports=equal_arrays(a,c)
        comparisons.append(dict(method=name,reference=reference['path'],first=first['path'],hot=hot['path'],
            first_comparisons=reports,hot_comparisons=hot_reports,hot_cache_hits=after['hits']-before['hits'],
            reference_seconds=reference['seconds'],first_seconds=first['seconds'],hot_seconds=hot['seconds'],
            paired_current_worker=True,models_and_schedules_identical=True))
    path=ROOT/'provenance/NATIVE_TRAINING_AB_PASS.json';atomic(path,dict(status='PASS',time=stamp(),all_weights_and_checkpoint_arrays_bitwise_equal=True,
        expert_and_hard_and_soft_validated=True,same_case_seed_schedule=True,comparisons=comparisons,
        scope='12-step training equivalence, cold/available and all-hit paths; separate sampler states and actual-score equality. Sustained throughput still requires observation.'))
    return dict(path=str(path.relative_to(ROOT)),methods=len(comparisons))
