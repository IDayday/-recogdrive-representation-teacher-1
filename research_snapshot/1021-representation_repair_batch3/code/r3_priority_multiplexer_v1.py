"""Retain Base services while three nodes prioritize batch4; new nodes run R3.

The three allocated nodes wait for their own evaluation executor/compute-done
marker. Later nodes immediately serve unchanged original scientific stages.
All switches occur after committed chunks. No job or main process is stopped.
"""
from r3_common import *
import importlib.util
import socket
import traceback

MODULES={}


def module(path,expected):
    assert sha(path)==expected;key=(str(path),expected)
    if key not in MODULES:
        spec=importlib.util.spec_from_file_location('priority_'+expected,path)
        result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);MODULES[key]=result
    return MODULES[key]


def run(engine,parent,pool):
    from r3_stage_service_v1 import claim
    registry=read(ROOT/'resources/REGISTRY.json')
    node=next(n for n in registry['nodes'] if socket.gethostname().startswith(n['job']+'-'))
    device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices']
    worker=dict(node=node['name'],job=node['job'],device=device,pid=os.getpid(),hostname=socket.gethostname(),lease=parent['id'])
    batch4=ROOT.parent/'1021-representation_distillation_batch4'
    assigned=next((n for n in read(batch4/'resources/ALLOCATION_V1.json')['nodes'] if n['job']==node['job']),None)
    live=ROOT/'runs/priority_multiplexer_workers'/(node['name']+'_device%02d_pid%d.json'%(device,os.getpid()))
    completed=0;private_executor=None
    while True:
        if assigned and not (batch4/'runs'/('GROUP_COMPUTE_COMPLETE_'+assigned['group']+'.json')).exists():
            descriptor=batch4/'runs/EVALUATION_EXECUTOR.json'
            if descriptor.exists():
                executor=read(descriptor);path=(batch4/executor['code']).resolve()
                assert path.is_relative_to(batch4/'code')
                private_executor=module(path,executor['sha256'])
                atomic(live,dict(status='SERVING_BATCH4_EVALUATION_OR_WAITING',time=stamp(),worker=worker,group=assigned['group'],completed=completed))
                if private_executor.run_one(engine,node,worker,pool):continue
            atomic(live,dict(status='RESERVED_FOR_BATCH4_TRAINING',time=stamp(),worker=worker,group=assigned['group'],completed=completed))
            time.sleep(10);continue
        if private_executor is not None:
            if hasattr(private_executor,'release_private_student'):private_executor.release_private_student()
            private_executor=None;engine.verify_engine()
        selected=claim(worker)
        if selected is None:
            atomic(live,dict(status='BATCH3_QUEUE_WAIT',time=stamp(),worker=worker,completed=completed));time.sleep(10);continue
        setting,task=selected;stage=ROOT/task['stage'];began=time.monotonic()
        atomic(live,dict(status='COMPUTING_BATCH3',time=stamp(),worker=worker,task=task['id'],stage=task['stage'],completed=completed))
        try:
            source=(ROOT/setting['handler']).resolve();assert source.is_relative_to(ROOT/'code')
            result=module(source,setting['handler_sha256']).run(engine,task,pool);engine.verify_engine()
            atomic(stage/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result,
                specification_sha256=setting['specification_sha256'],seconds=time.monotonic()-began));completed+=1
        except BaseException as error:
            proof=dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc())
            atomic(stage/'failures'/(task['id']+'.json'),proof)
            atomic(ROOT/parent['stage']/'failures'/(node['name']+'_pid%d.json'%os.getpid()),proof)
            return dict(status='FAILED_REQUIRES_AGENT_REVIEW',stage=task['stage'],task=task['id'])
