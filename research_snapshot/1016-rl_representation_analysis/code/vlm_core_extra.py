"""Use verified spare container CPU for unclaimed canonical grids; no GPU changes."""
from common import *
import argparse,subprocess
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT

def main(a):
    setup(f'vlm_repair/core_extra/node{a.node}')
    import psutil
    for p,h in read(VOUT/'CORE_EXTRA_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    cpu=psutil.cpu_percent(interval=2);memory=psutil.virtual_memory();assert os.cpu_count()>=160 and cpu<80 and memory.available>128*1024**3
    dest=VOUT/f'core_extra/node{a.node}';atomic(dest/'PREFLIGHT.json',dict(status='PASS',time=stamp(),cpus=os.cpu_count(),busy_percent=cpu,available_memory=memory.available,extra_workers=8,threads_per_worker=2,gpu_work_untouched=True))
    children=[];streams=[]
    for local in range(8):
        rank=48+a.node*8+local;stream=(dest/f'rank{rank:03d}.log').open('a');streams.append(stream)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_core_scan.py'),'worker','--rank',str(rank)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        bad=[dict(rank=48+a.node*8+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() is not None]
        if bad:atomic(VOUT/'failures'/f'core_extra_node{a.node}.json',dict(status='FAILED',time=stamp(),ranks=bad));raise RuntimeError(str(bad))
        atomic(dest/'STATUS.json',dict(status='RUNNING',time=stamp(),workers={48+a.node*8+i:p.pid for i,p in enumerate(children)},canonical_only=True))
        time.sleep(30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);main(p.parse_args())
