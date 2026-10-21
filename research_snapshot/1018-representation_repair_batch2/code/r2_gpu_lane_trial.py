"""Bounded one-card concurrency trial using unchanged real sweep work.

The primary worker continues. This process exits only at a task boundary, never
stops an existing process, and never releases a DLC node. Results use the same
atomic queue and exact native/seed/score checks as the primary sweep.
"""
from r2_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


def main(args):
    setup('gpu_lane_trial/'+args.node);compatibility()
    import torch
    from r2_gpu import init_score
    from r2_eval_rollouts import Fits,evaluate,claim_stage
    from vlm_intervene_v4 import Engine
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname()
    assert torch.cuda.device_count()==1
    free,total=torch.cuda.mem_get_info();assert free>30*1024**3
    destination=ROOT/'provenance/gpu_lane_trial'/args.node/f'device{args.device:02d}'
    assert not (destination/'START.json').exists()
    live=read(RUN/'nodes'/args.node/'LIVE.json');primary=live['children']['gpu_1_'+str(args.device)]['pid']
    began=time.monotonic();worker=socket.gethostname()+'_'+str(os.getpid())
    atomic(destination/'START.json',dict(time=stamp(),pid=os.getpid(),primary_pid=primary,worker=worker,
           node=args.node,device=args.device,duration_seconds=args.seconds,free_bytes=free,total_bytes=total,
           existing_primary_retained=True,scientific_handler_sha256=sha(ROOT/'code/r2_eval_rollouts.py')))
    engine=Engine();fits=Fits();base=ROOT/'runs/representation_coarse_v1';completed=[]
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score) as pool:
        while time.monotonic()-began<args.seconds:
            task=claim_stage(base,worker)
            if task is None:time.sleep(10);continue
            start=time.monotonic();result=evaluate(engine,task,base,pool,fits)
            record=dict(status='COMPLETE',time=stamp(),task=task,worker=worker,seconds=time.monotonic()-start,result=result)
            atomic(base/'receipts'/(task['id']+'.json'),record);completed.append(record)
            atomic(destination/'LIVE.json',dict(time=stamp(),completed=len(completed),seconds=time.monotonic()-began))
    engine.verify_engine()
    atomic(destination/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),seconds=time.monotonic()-began,
           worker=worker,primary_pid=primary,tasks=len(completed),records=sum(r['result']['records'] for r in completed),
           task_receipts=completed,original_process_stopped=False,node_released=False))
    print('CONCURRENCY_TRIAL_COMPLETE',len(completed),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--device',type=int,default=0)
    p.add_argument('--seconds',type=int,default=600);args=p.parse_args()
    try:main(args)
    except BaseException as error:
        import traceback
        atomic(ROOT/'provenance/gpu_lane_trial'/args.node/f'device{args.device:02d}'/'FAILURE.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
