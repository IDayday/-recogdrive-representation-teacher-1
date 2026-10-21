"""Persistent frozen model workers with versioned per-task scientific handlers."""
from r2_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import importlib.util
import multiprocessing as mp
import traceback


def init_score():
    setup('scorers/'+socket.gethostname()+'/'+str(os.getpid())); compatibility()


def main(args):
    setup(f'gpu/{args.node}/{args.device}'); compatibility()
    from vlm_intervene_v4 import Engine
    engine = Engine()
    worker = args.node+f'_gpu{args.device:02d}'
    status = RUN/'workers_gpu'/(worker+'.json')
    modules = {}
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score) as pool:
        while True:
            task=claim('gpu',worker)
            if task is None:
                atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank));time.sleep(10);continue
            began=time.monotonic(); atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id']))
            try:
                source=(ROOT/task['handler']).resolve()
                assert source.is_relative_to(ROOT/'code') and sha(source)==task['handler_sha256']
                key=task['handler_sha256']
                if key not in modules:
                    spec=importlib.util.spec_from_file_location('r2_gpu_handler_'+key,source)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[key]=module
                result=modules[key].run(engine,task,pool)
                engine.verify_engine()
                atomic(RUN/'receipts_gpu'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),
                       worker=worker,rank=args.rank,task=task,seconds=time.monotonic()-began,result=result))
            except BaseException as error:
                atomic(RUN/'failures_gpu'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),
                       worker=worker,rank=args.rank,task=task,error=repr(error),traceback=traceback.format_exc()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--device',type=int,required=True)
    p.add_argument('--rank',type=int,required=True);main(p.parse_args())
