"""Independent optional GPU lane for overlapping frozen sweeps with training.

The primary model worker, DLC main process, code and results are retained. This
lane claims the identical small sweep tasks and uses the original evaluator.
"""
from r2_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import traceback


def main(args):
    setup('gpu_background/'+args.node+'/'+str(args.device)+'/'+args.tag);compatibility()
    import torch
    from r2_gpu import init_score
    from r2_eval_rollouts import Fits,evaluate,claim_stage
    from vlm_intervene_v4 import Engine
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname() and torch.cuda.device_count()==1
    free,total=torch.cuda.mem_get_info();assert free>30*1024**3
    folder=RUN/'background_gpu'/args.node/f'device{args.device:02d}'/args.tag
    assert not (folder/'START.json').exists()
    began=time.monotonic();worker=socket.gethostname()+'_'+str(os.getpid());completed=[]
    atomic(folder/'START.json',dict(time=stamp(),worker=worker,pid=os.getpid(),node=args.node,device=args.device,
           seconds=args.seconds,free_bytes=free,total_bytes=total,evaluator_sha256=sha(ROOT/'code/r2_eval_rollouts.py')))
    engine=Engine();fits=Fits();config_path=ROOT/'config/BACKGROUND_GPU_STAGES.json'
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score) as pool:
        while not args.seconds or time.monotonic()-began<args.seconds:
            config=read(config_path);chosen=None
            if config.get('enabled',True):
                registry=read(ROOT/'config/GPU_STAGES.json');stages={s['path']:s for s in registry['stages']}
                for name in config['stages']:
                    stage=stages[name];assert stage['kind']=='rollouts'
                    assert stage['handler']=='code/r2_eval_rollouts.py' and stage['handler_sha256']==sha(ROOT/stage['handler'])
                    task=claim_stage(ROOT/name,worker)
                    if task is not None:chosen=(ROOT/name,task);break
            if chosen is None:
                atomic(folder/'LIVE.json',dict(time=stamp(),status='QUEUE_WAIT',completed=len(completed)));time.sleep(10);continue
            base,task=chosen;start=time.monotonic()
            atomic(folder/'LIVE.json',dict(time=stamp(),status='COMPUTING',stage=str(base.relative_to(ROOT)),task=task['id'],completed=len(completed)))
            try:
                result=evaluate(engine,task,base,pool,fits);engine.verify_engine()
                receipt=dict(status='COMPLETE',time=stamp(),task=task,worker=worker,seconds=time.monotonic()-start,result=result)
                atomic(base/'receipts'/(task['id']+'.json'),receipt);completed.append(receipt)
            except BaseException as error:
                detail=dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc())
                atomic(base/'failures'/(task['id']+'.json'),detail);atomic(RUN/'failures_gpu'/('background_'+task['id']+'.json'),detail)
                raise
    atomic(folder/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),seconds=time.monotonic()-began,
           tasks=len(completed),records=sum(d['result']['records'] for d in completed),worker=worker,
           receipts=completed,original_primary_stopped=False,node_released=False))
    print('BACKGROUND_TRIAL_COMPLETE',args.node,args.device,len(completed),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--device',type=int,required=True)
    p.add_argument('--tag',required=True);p.add_argument('--seconds',type=int,default=600);args=p.parse_args()
    try:main(args)
    except BaseException as error:
        atomic(RUN/'failures'/('background_'+args.node+'_'+str(args.device)+'_'+args.tag+'.json'),
               dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
