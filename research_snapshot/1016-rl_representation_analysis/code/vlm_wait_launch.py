"""Keep an in-container launcher ready; start a new GPU program after existing work drains."""
from common import *
import argparse,subprocess
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True);p.add_argument('--variant',type=int,required=True);args=p.parse_args();setup(f'vlm_repair/wait_launch/v{args.variant}/node{args.node}')
    assert args.variant==5
    old=ROOT/'runs/vlm_repair_20261016_v2';status=VOUT/f'launchers/v5_node{args.node}.json'
    while True:
        queued=len(read(old/'tasks.json'));done=len(list((old/'receipts').glob('*.json')));ready=(VOUT/'global_funnel/PARENT_LOCK.json').exists()
        atomic(status,dict(status='WAIT_CURRENT_COMPUTATION',time=stamp(),queued=queued,done=done,global_pool_frozen=ready,node=args.node))
        if ready and queued==done:break
        time.sleep(20)
    cmd=[sys.executable,'-u','-B',str(ROOT/'code/vlm_repair_queue_v5.py'),'node','--node',str(args.node),'--workers','16','--run','vlm_global_refine_20261016_v5']
    atomic(status,dict(status='STARTING_VERIFIED_NEW_PROGRAM',time=stamp(),node=args.node,variant=5))
    result=subprocess.run(cmd,cwd=ROOT)
    if result.returncode:atomic(VOUT/'failures'/f'v5_launcher_node{args.node}.json',dict(status='FAILED',time=stamp(),returncode=result.returncode));raise RuntimeError('v5 node exit')
