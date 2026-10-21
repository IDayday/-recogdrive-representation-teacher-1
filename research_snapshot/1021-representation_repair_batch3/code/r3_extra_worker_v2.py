"""Optional extra model lane on an existing card, using unchanged frozen tasks.

Admission requires all42 outputs/interfaces to equal the existing engineering
golden records. This changes scheduling only, never algorithms or seeds.
"""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import importlib.util
import multiprocessing as mp
import socket
import traceback


def main(a):
    assert os.environ.get('CUDA_VISIBLE_DEVICES')==str(a.device)
    setup('extra/'+a.node+'/'+str(a.device)+'/'+str(a.lane));compatibility()
    import torch
    from vlm_intervene_v4 import Engine
    from r3_runtime import init_scorer
    from r3_first42_rollout_v2 import run as engineering
    from r3_resident_service_v1 import claim
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node);assert socket.gethostname().startswith(node['job']+'-') and a.device in node['devices']
    free,total=torch.cuda.mem_get_info();assert free>32*(1<<30)
    worker=a.node+'_device%02d_lane%d'%(a.device,a.lane);dest=ROOT/'runs/extra_engineering_v1'/worker
    atomic(dest/'LIVE.json',dict(status='LOADING_MODEL',time=stamp(),pid=os.getpid(),free_bytes=free,node=a.node,device=a.device,lane=a.lane))
    engine=Engine();pack=ROOT/'manifests/first42_v1.json';rows=BATCH1/'manifests/natural_s0.json'
    meta=dict(worker=worker,node=a.node,job=node['job'],device=a.device,lane=a.lane,pid=os.getpid(),hostname=socket.gethostname(),extra_lane_on_existing_physical_card=True)
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        task=dict(id=worker+'_engineering',stage=str(dest.relative_to(ROOT)),indices=[60,1],pack=str(pack),pack_sha256=sha(pack),rows=str(rows),rows_sha256=sha(rows),cohort='navtrain',seeds=[0,1,2,3,4])
        result=engineering(engine,task,pool)
        for ref in read(ROOT/result['path'])['cases']:
            actual=read(ROOT/ref['path']);golden=read(ROOT/'runs/first42_engineering_v2/cases'/actual['token']/'RESULT.json')
            assert actual['records']==golden['records'] and actual['selection']==golden['selection']
        atomic(dest/'PASS.json',dict(status='PASS_ALL42_FIVE_NOISE_GOLDEN_EXACT',time=stamp(),worker=meta,result=result,freeze_unchanged=True))
        modules={};completed=0;live=ROOT/'runs/workers'/(worker+'.json')
        while True:
            if (dest/'DRAIN.json').exists():
                atomic(dest/'DRAINED.json',dict(status='DRAINED_AT_COMMITTED_BOUNDARY',time=stamp(),worker=meta,completed=completed))
                return
            task=claim(worker)
            if task is None:
                atomic(live,dict(status='QUEUE_WAIT',time=stamp(),completed=completed,**meta));time.sleep(10);continue
            atomic(live,dict(status='COMPUTING',time=stamp(),completed=completed,task=task['id'],stage=task['stage'],**meta));start=time.monotonic();folder=ROOT/task['stage']
            try:
                source=(ROOT/task['handler']).resolve();assert source.is_relative_to(ROOT/'code') and sha(source)==task['handler_sha256'];key=task['handler_sha256']
                if key not in modules:
                    spec=importlib.util.spec_from_file_location('r3_extra_'+key,source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[key]=module
                if source.name=='r3_first42_driver_v1.py':
                    from r3_first42_driver_v2 import run as drainable
                    result=drainable(engine,task,pool,drain_file=dest/'DRAIN.json')
                else:result=modules[key].run(engine,task,pool)
                engine.verify_engine()
                atomic(folder/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),worker=meta,task=task,result=result,seconds=time.monotonic()-start));completed+=1
            except BaseException as error:
                atomic(folder/'failures'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=meta,task=task,error=repr(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--device',type=int,required=True);p.add_argument('--lane',type=int,default=1);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/extra_engineering_v1'/(a.node+'_device%02d_lane%d'%(a.device,a.lane))/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
