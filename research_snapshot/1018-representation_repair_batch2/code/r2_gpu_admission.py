"""Prioritize selected canonical work without reordering a cursor-based queue.

The canonical claim is shared with original workers. No duplicated inference or
changed scientific configuration: this only admits early independent-fold work.
"""
from r2_common import *


def run(engine,task,pool):
    canonical=task['canonical_task'];base=ROOT/task['canonical_stage'];receipt=base/'receipts'/(canonical['id']+'.json')
    if receipt.exists():return dict(status='ALREADY_COMPLETE',canonical=canonical['id'])
    claim=base/'claims'/canonical['id'];claim.parent.mkdir(parents=True,exist_ok=True)
    try:claim.mkdir()
    except FileExistsError:return dict(status='ALREADY_CLAIMED',canonical=canonical['id'],scientific_work_not_duplicated=True)
    worker=socket.gethostname()+'_'+str(os.getpid());atomic(claim/'OWNER.json',dict(worker=worker,time=stamp(),pid=os.getpid(),hostname=socket.gethostname(),admission_task=task['id']))
    assert task['handler_sha256_expected']==sha(ROOT/'code/r2_cached_training_bridge.py')
    from r2_cached_training_bridge import run as execute
    began=time.monotonic();result=execute(engine,canonical,pool);engine.verify_engine()
    atomic(receipt,dict(status='COMPLETE',time=stamp(),task=canonical,worker=worker,seconds=time.monotonic()-began,result=result,admission_task=task['id']))
    return dict(status='COMPLETE',canonical=canonical['id'],result=result,seconds=time.monotonic()-began)
