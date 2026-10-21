"""Elastic persistent leases over a finite first42 worklist.

Small outer leases avoid quadratic rescans of the resident dispatch queue.
Each work item commits scene results before its receipt. No cloud/job changes.
"""
from r3_common import *
import socket
import traceback

CURSORS={}


def run(engine,lease,pool):
    from r3_first42_rollout_v2 import loaded,run as evaluate
    stage=ROOT/lease['work_stage'];tasks=loaded(str(stage/'tasks.json'),lease['worklist_sha256']);key=str(stage)
    cursor=CURSORS.get(key,0);done=0;began=time.monotonic()
    worker=dict(hostname=socket.gethostname(),pid=os.getpid(),device=os.environ.get('CUDA_VISIBLE_DEVICES'),lease=lease['id'])
    live=stage/'workers'/(worker['hostname']+'_'+str(worker['pid'])+'.json')
    while cursor<len(tasks):
        task=tasks[cursor];cursor+=1;CURSORS[key]=cursor
        receipt=stage/'receipts'/(task['id']+'.json')
        if receipt.exists():continue
        claim=stage/'claims'/task['id'];claim.parent.mkdir(parents=True,exist_ok=True)
        try:claim.mkdir()
        except FileExistsError:continue
        atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,task=task))
        atomic(live,dict(status='COMPUTING',time=stamp(),worker=worker,task=task['id'],completed=done));start=time.monotonic()
        try:
            assert sha(ROOT/'code/r3_first42_rollout_v2.py')==lease['evaluation_sha256']
            result=evaluate(engine,task,pool)
            atomic(receipt,dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result,seconds=time.monotonic()-start));done+=1
        except BaseException as error:
            atomic(stage/'failures'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc()))
            raise
    atomic(live,dict(status='LEASE_FINISHED_ALL_REMAINING_ITEMS_CLAIMED',time=stamp(),worker=worker,completed=done))
    return dict(work_stage=lease['work_stage'],completed=done,seconds=time.monotonic()-began)
