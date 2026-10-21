"""Execute unchanged scientific tasks under their original atomic claims.

An independent metadata queue can balance experiment families without reordering
frozen cursor queues, duplicating inference, replacing a model worker or stopping
in-flight work. Canonical receipts remain the sole scientific completion record.
"""
from r2_common import *
import importlib.util

MODULES={}


def run(engine,task,pool):
    canonical=task['canonical_task'];base=ROOT/task['canonical_stage'];receipt=base/'receipts'/(canonical['id']+'.json')
    if receipt.exists():return dict(status='ALREADY_COMPLETE',canonical=canonical['id'])
    claim=base/'claims'/canonical['id'];claim.parent.mkdir(parents=True,exist_ok=True)
    try:claim.mkdir()
    except FileExistsError:return dict(status='ALREADY_CLAIMED',canonical=canonical['id'],no_duplicate_scientific_work=True)
    worker=socket.gethostname()+'_'+str(os.getpid());atomic(claim/'OWNER.json',dict(worker=worker,time=stamp(),pid=os.getpid(),hostname=socket.gethostname(),admission_task=task['id']))
    stage=task['scientific_handler'];source=ROOT/stage['handler'];key=stage['handler_sha256'];assert sha(source)==key and source.resolve().is_relative_to(ROOT/'code')
    if key not in MODULES:
        spec=importlib.util.spec_from_file_location('admitted_science_'+key,source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);MODULES[key]=module
    module=MODULES[key];began=time.monotonic()
    try:
        if stage['kind']=='rollouts':
            if not hasattr(module,'_admission_fits'):module._admission_fits=module.Fits()
            result=module.evaluate(engine,canonical,base,pool,module._admission_fits)
        else:result=module.run(engine,canonical,pool)
        engine.verify_engine()
        atomic(receipt,dict(status='COMPLETE',time=stamp(),task=canonical,worker=worker,seconds=time.monotonic()-began,result=result,admission_task=task['id'],scientific_handler=stage))
        return dict(status='COMPLETE',canonical=canonical['id'],result=result,seconds=time.monotonic()-began)
    except BaseException as error:
        import traceback
        atomic(base/'failures'/(canonical['id']+'.json'),dict(status='FAILED',time=stamp(),task=canonical,worker=worker,error=repr(error),traceback=traceback.format_exc(),admission_task=task['id']))
        raise
