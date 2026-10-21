"""Elastic finite-chunk stages served by retained models, no fixed rank count.

A stage has one immutable template and a compact index layout. Workers choose
the earliest eligible stage at committed chunk boundaries. Unblocked later
training stages can compute while the agent audits an earlier stage. Test
stages require explicit acceptance files and a frozen test lock.
"""
from r3_common import *
import importlib.util
import socket
import traceback
from functools import lru_cache

CURSORS={}
QUEUE_VERSION=None
QUEUE=None
MODULES={}
QUEUE_PATH=ROOT/'runs/ELASTIC_STAGE_QUEUE.json'


@lru_cache(maxsize=8)
def descriptor(path,expected):
    assert sha(path)==expected
    return read(path)


def stages():
    global QUEUE_VERSION,QUEUE
    path=QUEUE_PATH;version=retry(lambda:path.stat().st_mtime_ns)
    if version!=QUEUE_VERSION:QUEUE=read(path);QUEUE_VERSION=version
    return QUEUE


def claim(worker):
    queue=stages()
    for setting in sorted(queue['stages'],key=lambda v:(v['priority'],v['id'])):
        if any(not retry(lambda p=p:(ROOT/p).exists()) for p in setting.get('requires',[])):continue
        stage=ROOT/setting['stage']
        if next((stage/'failures').glob('*.json'),None) is not None:continue
        if retry(lambda:(stage/'COMPUTE_COMPLETE.json').exists()):continue
        spec=descriptor(str(stage/'SPECIFICATION.json'),setting['specification_sha256'])
        count=spec['case_count'];size=spec['chunk_size'];key=str(stage)
        if 'indices_path' in spec:
            indices=descriptor(spec['indices_path'],spec['indices_sha256'])
            assert len(indices)==count
        else:indices=None
        cursor=CURSORS.get(key,0)
        while cursor<count:
            offset=cursor;cursor+=size;CURSORS[key]=cursor
            ident=setting['id']+'_%06d'%offset;receipt=stage/'receipts'/(ident+'.json')
            if retry(lambda:receipt.exists()):continue
            claimed=stage/'claims'/ident;claimed.parent.mkdir(parents=True,exist_ok=True)
            try:retry(lambda:claimed.mkdir())
            except FileExistsError:continue
            chosen=list(range(offset,min(offset+size,count))) if indices is None else indices[offset:offset+size]
            task=dict(spec['task_template'],id=ident,stage=str(stage.relative_to(ROOT)),indices=chosen)
            atomic(claimed/'OWNER.json',dict(time=stamp(),worker=worker,task=task,specification_sha256=setting['specification_sha256']))
            return setting,task
    return None


def run(engine,parent,pool):
    registry=read(ROOT/'resources/REGISTRY.json')
    node=next(n for n in registry['nodes'] if socket.gethostname().startswith(n['job']+'-'))
    device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices']
    worker=dict(node=node['name'],job=node['job'],hostname=socket.gethostname(),pid=os.getpid(),device=str(device),lease=parent['id'])
    live=ROOT/'runs/elastic_stage_workers'/(worker['hostname']+'_'+str(worker['pid'])+'.json');completed=0
    while True:
        selected=claim(worker)
        if selected is None:
            queue=stages()
            if not queue.get('open',True) and all((ROOT/v['stage']/'COMPUTE_COMPLETE.json').exists() for v in queue['stages']):
                return dict(status='FINITE_REGISTERED_STAGES_COMPUTED',completed=completed,no_nodes_released=True)
            atomic(live,dict(status='QUEUE_WAIT',time=stamp(),worker=worker,completed=completed));time.sleep(10);continue
        setting,task=selected;stage=ROOT/task['stage'];began=time.monotonic()
        atomic(live,dict(status='COMPUTING',time=stamp(),worker=worker,task=task['id'],stage=task['stage'],completed=completed))
        try:
            source=(ROOT/setting['handler']).resolve();assert source.is_relative_to(ROOT/'code') and sha(source)==setting['handler_sha256']
            key=setting['handler_sha256']
            if key not in MODULES:
                module_spec=importlib.util.spec_from_file_location('r3_elastic_'+key,source);module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module);MODULES[key]=module
            result=MODULES[key].run(engine,task,pool);engine.verify_engine()
            atomic(stage/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result,
                   specification_sha256=setting['specification_sha256'],seconds=time.monotonic()-began));completed+=1
        except BaseException as error:
            atomic(stage/'failures'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc()))
            atomic(live,dict(status='FAILED_REQUIRES_AGENT_REVIEW',time=stamp(),worker=worker,task=task['id']))
            # Keep the retained main process available to the outer dispatcher.
            return dict(status='FAILED_REQUIRES_AGENT_REVIEW',stage=task['stage'],task=task['id'])
