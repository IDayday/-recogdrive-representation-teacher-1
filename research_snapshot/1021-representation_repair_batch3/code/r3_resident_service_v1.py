"""Elastic third-batch service inside original retained model workers.

Compatibility queue claims remain in the existing dispatcher. Scientific tasks,
outputs, and receipts use the independent third-batch root. No signals or job
operations; other resident parents and old queues remain alive/open.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r3_common import *
import importlib.util
import socket
import traceback


def claim(worker):
    registry=ROOT/'runs/QUEUE.json'
    if not registry.exists():return None
    for task in read(registry)['tasks']:
        folder=ROOT/task['stage']
        if (folder/'receipts'/(task['id']+'.json')).exists():continue
        claimed=folder/'claims'/task['id'];claimed.parent.mkdir(parents=True,exist_ok=True)
        try:claimed.mkdir()
        except FileExistsError:continue
        atomic(claimed/'OWNER.json',dict(time=stamp(),worker=worker,pid=os.getpid(),hostname=socket.gethostname(),task=task))
        return task
    return None


def run(engine,parent,pool):
    setup('resident/'+socket.gethostname()+'/'+str(os.getpid()));compatibility()
    registry=read(ROOT/'resources/REGISTRY.json');node=next(n for n in registry['nodes'] if socket.gethostname().startswith(n['job']+'-'))
    device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices'];worker=node['name']+'_device%02d'%device
    meta=dict(worker=worker,node=node['name'],job=node['job'],device=device,pid=os.getpid(),hostname=socket.gethostname())
    status=ROOT/'runs/workers'/(worker+'.json');completed=0;modules={}
    atomic(status,dict(status='ENGINEERING',time=stamp(),**meta))
    from r3_engineering_handler_v1 import run as engineering
    if not (ROOT/'runs/resident_engineering_v1'/node['name']/('device%02d'%device)/'PASS.json').exists():
        try:engineering(engine,dict(node=node['name'],job=node['job'],device=device),pool)
        except BaseException as error:
            atomic(ROOT/'runs/resident_engineering_v1'/node['name']/('device%02d'%device)/'FAILED.json',dict(status='FAILED',time=stamp(),**meta,error=repr(error),traceback=traceback.format_exc()))
            raise
    while True:
        if not (ROOT/'resources/nodes'/node['name']/'THIRD_BATCH_GPU_ACCEPTED.json').exists():
            atomic(status,dict(status='NODE_ENGINEERING_ACCEPTANCE_WAIT',time=stamp(),completed=completed,**meta));time.sleep(5);continue
        task=claim(worker)
        if task is None:
            atomic(status,dict(status='QUEUE_WAIT',time=stamp(),completed=completed,**meta));time.sleep(10);continue
        folder=ROOT/task['stage'];began=time.monotonic();atomic(status,dict(status='COMPUTING',time=stamp(),task=task['id'],stage=task['stage'],completed=completed,**meta))
        try:
            path=(ROOT/task['handler']).resolve();assert path.is_relative_to(ROOT/'code') and sha(path)==task['handler_sha256'];key=task['handler_sha256']
            if key not in modules:
                spec=importlib.util.spec_from_file_location('r3_task_'+key,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[key]=module
            result=modules[key].run(engine,task,pool);engine.verify_engine()
            atomic(folder/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),worker=meta,task=task,result=result,seconds=time.monotonic()-began));completed+=1
        except BaseException as error:
            atomic(folder/'failures'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=meta,task=task,error=repr(error),traceback=traceback.format_exc()))
            atomic(status,dict(status='TASK_FAILED_REQUIRES_REVIEW',time=stamp(),task=task['id'],**meta))
            # Avoid an unobserved repeated failure consuming the remaining queue.
            return dict(status='TASK_FAILED_REQUIRES_REVIEW',task=task['id'],worker=meta)
