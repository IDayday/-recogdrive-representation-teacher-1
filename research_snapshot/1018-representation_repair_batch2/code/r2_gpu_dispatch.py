"""Elastic, priority-aware scientific stages on retained model workers.

All scientific handlers remain immutable. Only stage metadata changes; a worker
can switch to a newly available valuable stage at its next small task boundary.
"""
from r2_common import *
from r2_eval_rollouts import claim_stage
import importlib.util
import traceback


def run(engine,parent,pool):
    registry=ROOT/'config/GPU_STAGES.json';worker=socket.gethostname()+'_'+str(os.getpid())
    modules={};completed=0;version=None;stages=[]
    while True:
        current=registry.stat().st_mtime_ns
        if current!=version:
            config=read(registry);stages=sorted(config['stages'],key=lambda s:s['priority']);version=current
            if config.get('close_dispatchers'):return dict(completed=completed,retained_nodes=True)
        chosen=None
        for stage in stages:
            if not stage.get('enabled',True):continue
            base=ROOT/stage['path'];task=claim_stage(base,worker)
            if task is not None:chosen=(stage,base,task);break
        if chosen is None:
            atomic(RUN/'dispatch_workers'/(worker+'.json'),dict(status='QUEUE_WAIT',time=stamp(),completed=completed))
            time.sleep(10);continue
        stage,base,task=chosen;began=time.monotonic()
        atomic(base/'workers'/(worker+'.json'),dict(status='COMPUTING',time=stamp(),task=task['id'],completed=completed))
        atomic(RUN/'dispatch_workers'/(worker+'.json'),dict(status='COMPUTING',time=stamp(),stage=stage['path'],task=task['id']))
        try:
            key=stage['handler_sha256'];source=ROOT/stage['handler']
            assert source.resolve().is_relative_to(ROOT/'code') and sha(source)==key
            if key not in modules:
                spec=importlib.util.spec_from_file_location('stage_'+key,source)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[key]=module
            module=modules[key]
            if stage['kind']=='rollouts':
                if not hasattr(module,'_dispatch_fit_cache'):module._dispatch_fit_cache=module.Fits()
                result=module.evaluate(engine,task,base,pool,module._dispatch_fit_cache)
            else:
                result=module.run(engine,task,pool)
            engine.verify_engine()
            atomic(base/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=task,
                   worker=worker,seconds=time.monotonic()-began,result=result))
            completed+=1
        except BaseException as error:
            detail=dict(status='FAILED',time=stamp(),task=task,worker=worker,error=repr(error),traceback=traceback.format_exc())
            atomic(base/'failures'/(task['id']+'.json'),detail)
            atomic(RUN/'failures_gpu'/('dispatch_'+task['id']+'.json'),detail)
        atomic(base/'workers'/(worker+'.json'),dict(status='TASK_BOUNDARY',time=stamp(),completed=completed))
