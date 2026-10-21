"""Complete a 64-cell corrected-grid wave with spare, low-priority CPU workers."""
from common import *
import argparse,subprocess
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup(f'vlm_semantic_v2/cpu_wave/node{a.node}')
    while not (SEM/'ANALYSIS_EXECUTION.json').exists():time.sleep(30)
    import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    for p,h in read(SEM/'CPU_WAVE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    ranks=list(range(48+a.node*16,56+a.node*16));folder=SEM/f'cpu_wave/node{a.node}';children=[];streams=[];checked=False
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),node=a.node,ranks=ranks,workers=8,threads=2,nice=10,memory_available=psutil.virtual_memory().available))
    for rank in ranks:
        stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_semantic_cpu.py'),'worker','--kind','scan','--rank',str(rank),'--workers','64','--threads','2'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10)))
    while True:
        bad=[dict(rank=r,returncode=p.returncode) for r,p in zip(ranks,children) if p.poll() is not None]
        if bad:atomic(SEM/f'cpu_wave/failures/node{a.node}.json',dict(status='FAILED',time=stamp(),ranks=bad));raise RuntimeError(str(bad))
        if not checked and all((SEM/f'scan/smoke/rank{r:03d}.json').exists() for r in ranks):atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=ranks,actual_numeric_reference_checked=True));checked=True
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),node=a.node,workers={r:p.pid for r,p in zip(ranks,children)}));time.sleep(30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);main(p.parse_args())
