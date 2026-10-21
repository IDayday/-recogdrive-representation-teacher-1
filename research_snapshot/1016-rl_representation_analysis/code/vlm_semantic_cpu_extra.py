"""Additional corrected-grid CPU workers, same frozen mathematics and references."""
from common import *
import argparse,subprocess
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup(f'vlm_semantic_v2/cpu_extra/node{a.node}')
    while not (SEM/'ANALYSIS_EXECUTION.json').exists():time.sleep(30)
    import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    for p,h in read(SEM/'CPU_EXTRA_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    # Original workers use ranks 0..15 with 8 workers/node. These disjoint ranks
    # use divisor 32 solely for local-owner preference and existing node gates:
    # 16..31 -> node0, 32..47 -> node1. All 48 ranks share atomic task claims.
    ranks=list(range(16+a.node*16,32+a.node*16));folder=SEM/f'cpu_extra/node{a.node}';children=[];streams=[];checked=False
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),node=a.node,ranks=ranks,workers=16,threads_per_worker=2,memory_available=psutil.virtual_memory().available))
    for rank in ranks:
        stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_semantic_cpu.py'),'worker','--kind','scan','--rank',str(rank),'--workers','32','--threads','2'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        failed=[dict(rank=r,returncode=p.returncode) for r,p in zip(ranks,children) if p.poll() is not None]
        if failed:atomic(SEM/f'cpu_extra/failures/node{a.node}.json',dict(status='FAILED',time=stamp(),ranks=failed));raise RuntimeError(str(failed))
        if not checked and all((SEM/f'scan/smoke/rank{r:03d}.json').exists() for r in ranks):
            atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=ranks,actual_numeric_reference_checked=True,mathematics_unchanged=True));checked=True
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),node=a.node,workers={r:p.pid for r,p in zip(ranks,children)}));time.sleep(30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);main(p.parse_args())
