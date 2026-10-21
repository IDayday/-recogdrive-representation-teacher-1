"""Immutable per-worker Base trajectories/states for training only, paired seeds.

Cache hits never change a target or sampler. The first request warms the actual
sampler; every actual S0 computation is checked against the frozen baseline. All
gradient predictions still reseed and execute the complete native denoising chain.
"""
from r2_common import *
from collections import OrderedDict


def native(engine,features,hidden,row,noise,need_states=False):
    import torch
    import numpy as np
    from repair_engine import baseline_row
    assert row['subset']=='exploration'
    if not hasattr(engine,'immutable_native_cache'):
        engine.immutable_native_cache=OrderedDict();engine.immutable_native_warmed=False
        engine.immutable_native_counts=dict(hits=0,archive_S0_hits=0,fresh=0,state_upgrades=0)
    key=(row['token'],row['metric_cache'],int(noise));cache=engine.immutable_native_cache;stats=engine.immutable_native_counts
    existing=cache.get(key)
    if existing is not None and (not need_states or existing[1] is not None):
        cache.move_to_end(key);stats['hits']+=1;return existing
    if existing is None and noise==0 and not need_states and engine.immutable_native_warmed:
        reference=baseline_row(row);trajectory=torch.as_tensor(np.asarray(reference['trajectory'],dtype=np.float32),device='cuda').clone()
        result=(trajectory,None);cache[key]=result;stats['archive_S0_hits']+=1
    else:
        original=engine.agent.action_head.p_mean_variance;states=[]
        def traced(x,*a,**kw):states.append(x.detach().clone());return original(x,*a,**kw)
        engine.agent.action_head.p_mean_variance=traced
        try:trajectory=engine.trajectory(features,hidden,seed(row['token'],noise))
        finally:engine.agent.action_head.p_mean_variance=original
        assert len(states)==5
        if noise==0:assert np.array_equal(trajectory.cpu().numpy(),baseline_row(row)['trajectory'])
        if existing is not None:assert torch.equal(existing[0],trajectory);stats['state_upgrades']+=1
        result=(trajectory.detach().clone(),torch.stack(states).squeeze(1).detach());cache[key]=result
        stats['fresh']+=1;engine.immutable_native_warmed=True
    cache.move_to_end(key)
    while len(cache)>16384:cache.popitem(last=False)
    return result
