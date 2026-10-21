"""Prepare verified next-stage workers inside the already retained jobs."""
from common import *
import argparse,subprocess
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True);a=p.parse_args();setup(f'vlm_repair/wait_launch/v6/node{a.node}');old=ROOT/'runs/vlm_repair_20261016_v2'
    while True:
        queued=len(read(old/'tasks.json'));done=len(list((old/'receipts').glob('*.json')));ready=(VOUT/'global_funnel/PARENT_LOCK.json').exists()
        atomic(VOUT/f'launchers/v6_node{a.node}.json',dict(status='WAIT_CURRENT_COMPUTATION',time=stamp(),queued=queued,done=done,global_pool_frozen=ready,node=a.node))
        if ready and queued==done:break
        time.sleep(20)
    atomic(VOUT/f'launchers/v6_node{a.node}.json',dict(status='STARTING_VERIFIED_NEW_PROGRAM',time=stamp(),node=a.node))
    ret=subprocess.run([sys.executable,'-u','-B',str(ROOT/'code/vlm_repair_queue_v6.py'),'node','--node',str(a.node),'--workers','16','--run','vlm_global_refine_20261016_v5'],cwd=ROOT)
    if ret.returncode:atomic(VOUT/'failures'/f'v6_launcher_node{a.node}.json',dict(status='FAILED',time=stamp(),returncode=ret.returncode));raise RuntimeError('v6 node exit')
