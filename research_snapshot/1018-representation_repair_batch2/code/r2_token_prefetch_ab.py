"""Verify ordered multi-reader input prefetch keeps every critic parameter exact."""
from r2_common import *


def run(engine,task,pool):
    from r2_token_critic import run as baseline
    from r2_token_critic_prefetch_v2 import run as optimized
    from r2_native_training_ab import equal_arrays
    config=read(ROOT/'runs/token_critic_pilot_v1/tasks.json')[0]
    reference=baseline(engine,dict(config,id='token_prefetch_ab_reference'),pool)
    candidate=optimized(engine,dict(config,id='token_prefetch_ab_v2'),pool)
    old=read(ROOT/reference['path']);new=read(ROOT/candidate['path']);reports=equal_arrays(old,new)
    assert [(r['index'],r['seed_index'],r['candidate_source']) for r in old['trace']]==[(r['index'],r['seed_index'],r['candidate_source']) for r in new['trace']]
    path=ROOT/'provenance/TOKEN_PREFETCH_AB_PASS.json';atomic(path,dict(status='PASS',time=stamp(),all_arrays_bitwise_equal=True,case_and_noise_schedule_equal=True,comparisons=reports,
        baseline_seconds=old['seconds'],prefetch_seconds=new['seconds'],baseline_input_wait=old['input_wait_seconds'],prefetch_input_wait=new['input_wait_seconds'],
        independent_versions=True,readers=4,depth=8,scope='16-step same-worker engineering A/B; observe sustained throughput before interpreting speed.'))
    return dict(path=str(path.relative_to(ROOT)),baseline_seconds=old['seconds'],prefetch_seconds=new['seconds'])
