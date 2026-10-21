"""Task-owned in-container CPU controllers; child completion never ends the DLC job."""
from common import *
import argparse,subprocess,traceback
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

SCRIPTS={'funnel':'vlm_funnel.py','replay':'vlm_replay.py','residual':'vlm_residual_candidates.py','global':'vlm_global_funnel.py','schedule':'vlm_scan_schedule.py'}

def main(args):
    setup(f'vlm_repair/controllers/node{args.node}');execution=read(VOUT/'CONTROLLER_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    names=['funnel'] if args.node==0 else ['replay','residual','global','schedule'];folder=VOUT/f'controllers/node{args.node}';folder.mkdir(parents=True,exist_ok=True);processes={};streams={};finished=set()
    for name in names:
        stream=(folder/(name+'.log')).open('a');streams[name]=stream;cmd=[sys.executable,'-u','-B',str(ROOT/'code'/SCRIPTS[name])]
        if name=='schedule':cmd.append('follow')
        processes[name]=subprocess.Popen(cmd,cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1'),stdout=stream,stderr=subprocess.STDOUT)
    atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),node=args.node,controllers={n:p.pid for n,p in processes.items()}))
    while True:
        states={}
        for name,p in processes.items():
            status=p.poll();states[name]=dict(pid=p.pid,status='RUNNING' if status is None else 'COMPLETE' if status==0 else 'FAILED',returncode=status)
            if status is not None and status!=0:
                atomic(VOUT/'failures'/f'controller_{name}.json',dict(status='FAILED',time=stamp(),node=args.node,controller=name,pid=p.pid,returncode=status,original_log=str((folder/(name+'.log')).relative_to(ROOT))))
        atomic(folder/'STATUS.json',dict(time=stamp(),node=args.node,controllers=states,job_and_gpu_queues_retained=True));time.sleep(30)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True);args=p.parse_args();main(args)
