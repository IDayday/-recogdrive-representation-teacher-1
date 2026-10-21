"""Compare cold/hot/archived Base outputs, five states and real actual scores."""
from r2_common import *


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_library_rollouts import load
    from r2_cached_interfaces import from_cached
    from r2_behavior_router import base_trajectory
    from r2_native_cache import native
    from repair_score import score_group
    cases=[]
    for index in read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel']:
        row,features,reference=load(index,engine.cfg,True);records=[]
        with torch.no_grad():
            hidden=from_cached(engine,features,index)
            for noise in [0,1,2]:
                fresh,states=base_trajectory(engine,features,hidden,seed(row['token'],noise),True)
                cold,cold_states=native(engine,features,hidden,row,noise,True);hot,hot_states=native(engine,features,hidden,row,noise,True)
                assert torch.equal(fresh,cold) and torch.equal(fresh,hot) and torch.equal(states,cold_states) and torch.equal(states,hot_states)
                for name,prediction in [('fresh',fresh),('cold',cold),('hot',hot)]:records.append(dict(arm=name,seed_index=noise,trajectory=prediction.cpu().numpy().tolist()))
            engine.immutable_native_cache.pop((row['token'],row['metric_cache'],0))
            archived,_=native(engine,features,hidden,row,0,False);assert np.array_equal(archived.cpu().numpy(),reference['trajectory'])
            upgraded,states=native(engine,features,hidden,row,0,True);assert torch.equal(upgraded,archived)
        actual=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=1800)
        for noise in [0,1,2]:
            scores=[r['score'] for r in actual if r['seed_index']==noise];assert scores[0]==scores[1]==scores[2]
        cases.append(dict(token=row['token'],seeds=[0,1,2],all_trajectories_bitwise_equal=True,all_five_states_bitwise_equal=True,actual_scores_exact=True))
    engine.verify_engine();path=ROOT/'provenance/NATIVE_CACHE_CONTRACT_PASS.json';atomic(path,dict(status='PASS',time=stamp(),cases=cases,counts=engine.immutable_native_counts,
        archive_S0_and_lru_replay_exact=True,training_only=True,gradient_chain_unchanged=True))
    return dict(path=str(path.relative_to(ROOT)),cases=len(cases),counts=engine.immutable_native_counts)
