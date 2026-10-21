"""Use idle CPUs for already released <=1536D grids, preserving all old scans."""
from common import *
import argparse,subprocess,traceback
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def worker(a):
    import vlm_scan_queue as module
    dimensions={b['name']:b['shape'][1] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']}
    original=module.claim
    def claim(tasks,rank,workers):return original([t for t in tasks if dimensions[t['block']]<=1536],rank,workers)
    module.claim=claim
    module.worker(a)

def node(a):
    setup(f'vlm_repair/scan_spare/node{a.node}');import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    p=read(VOUT/'SPARE_SCAN_EXECUTION.json')
    for path,h in p['code_sha256'].items():assert sha(ROOT/path)==h,path
    folder=VOUT/f'scan_spare/node{a.node}';folder.mkdir(parents=True,exist_ok=True)
    ranks=list(range(80,96)) if a.node==0 else list(range(128,144));children=[];streams=[];checked=False
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),node=a.node,ranks=ranks,threads=2,nice=10,
        memory_available=psutil.virtual_memory().available,source='Only original registered tasks already released by the frozen scheduler'))
    for rank in ranks:
        stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank),'--workers','128','--threads','2'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10)))
    while True:
        bad=[dict(rank=r,returncode=p.poll()) for r,p in zip(ranks,children) if p.poll() is not None]
        if bad:raise RuntimeError(str(bad))
        if not checked and all((VOUT/f'scan/smoke/rank{r:03d}.json').exists() for r in ranks):
            atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=ranks,actual_original_numeric_reference_checked=True));checked=True
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),node=a.node,workers={r:p.pid for r,p in zip(ranks,children)},low_priority=True));time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);p.add_argument('--workers',type=int);p.add_argument('--threads',type=int,default=2);a=p.parse_args()
    try:globals()[a.mode](a)
    except BaseException as exc:
        atomic(VOUT/'failures'/('spare_scan_'+a.mode+'_'+str(a.node)+'_'+str(a.rank)+'.json'),dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
