"""Compare all saved arrays and sampled losses for the raw/cached training A/B."""
from r2_common import *


def run(task):
    import numpy as np
    old=read(ROOT/'learned_experts/learned_prefetch_noise_pilot_v2/TRAINING.json')
    new=read(ROOT/'learned_experts/learned_cached_ab_pilot_v3/TRAINING.json');comparisons=[]
    assert len(old['checkpoints'])==len(new['checkpoints'])
    for a,b in zip(old['checkpoints'],new['checkpoints']):
        assert a['step']==b['step']
        with np.load(ROOT/a['path']) as x,np.load(ROOT/b['path']) as y:
            assert x.files==y.files
            differences={k:float(np.max(np.abs(x[k]-y[k]))) for k in x.files}
            assert all(v==0 for v in differences.values()),differences
        comparisons.append(dict(step=a['step'],all_arrays_bitwise_equal=True,max_abs_difference=differences))
    assert [(r['index'],r['seed_index']) for r in old['records']]==[(r['index'],r['seed_index']) for r in new['records']]
    result=dict(status='PASS',time=stamp(),comparisons=comparisons,raw_seconds=old['seconds'],cached_seconds=new['seconds'],
                runtime_ratio=new['seconds']/old['seconds'],training_weights_bitwise_equal=True,case_and_seed_schedule_equal=True,
                scope='12-step engineering A/B plus separate raw/cache state/mask/gradient/trajectory/score equality. Long-run throughput checked separately.')
    path=ROOT/'provenance/CACHED_TRAINING_AB_PASS.json';atomic(path,result);return result
