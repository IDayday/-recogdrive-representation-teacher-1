"""Small real sweep benchmark before adopting the new intervention producer."""
from r2_common import *
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from r2_gpu import init_score


def main():
    setup('eval_smoke_v2');compatibility()
    from vlm_intervene_v4 import Engine
    from r2_eval_rollouts import Fits,evaluate
    base=ROOT/'runs/eval_smoke_v2'
    engine=Engine()
    task=dict(id='real_operator_sweep',point='config/EVAL_SMOKE_POINT_v2.json',start=0,end=2)
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score) as pool:
        result=evaluate(engine,task,base,pool,Fits())
    engine.verify_engine()
    atomic(ROOT/'provenance/EVAL_SMOKE_PASS_v2.json',dict(status='PASS',time=stamp(),result=result,
           actual_subgroup_refits=True,prefetch=True,batched_device_return=True,independent_scoring=True))
    print('EVAL_SWEEP_SMOKE_PASS',result,flush=True)


if __name__=='__main__':main()
