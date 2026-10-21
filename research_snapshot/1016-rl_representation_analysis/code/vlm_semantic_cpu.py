"""Use the same verified CPU mathematics on corrected, separately versioned text pools."""
from common import *
import argparse,subprocess,traceback
from vlm_semantic import SEM
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def worker(a):
    import vlm_scan,vlm_scan_queue,vlm_rapid,vlm_rapid_queue
    vlm_scan.VOUT=SEM;vlm_scan_queue.VOUT=SEM;vlm_rapid.VOUT=SEM;vlm_rapid_queue.VOUT=SEM
    module=vlm_scan_queue if a.kind=='scan' else vlm_rapid_queue
    computation=vlm_scan if a.kind=='scan' else vlm_rapid
    original=computation.scan
    def checked(cell,*args,**kwargs):
        proof=read(SEM/'cells'/(cell+'.json'))
        constant=proof.get('constant_across_cases')
        if constant is None:
            import numpy as np
            x=np.load(ROOT/proof['path'],mmap_mode='r');sample=x[:min(256,len(x))]
            constant=bool(np.array_equal(sample,np.broadcast_to(x[0],sample.shape)) and np.array_equal(x,np.broadcast_to(x[0],x.shape)))
        if constant:
            result=dict(status='INELIGIBLE',time=stamp(),cell=cell,reason='exactly constant pooled representation across every scene, no behavior-quality discrimination possible',source_sha256=proof['sha256'],valid_cases=proof['valid_cases'])
            path=SEM/a.kind/'results'/(cell+'.json')
            if not path.exists():atomic(path,result)
            return read(path)
        return original(cell,*args,**kwargs)
    computation.scan=checked;module.worker(a)

def node(a):
    setup(f'vlm_semantic_v2/cpu/{a.kind}/node{a.node}')
    while not (SEM/'ANALYSIS_EXECUTION.json').exists():time.sleep(30)
    for p,h in read(SEM/'ANALYSIS_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    folder=SEM/a.kind/f'node{a.node}';folder.mkdir(parents=True,exist_ok=True);(SEM/a.kind/'claims').mkdir(exist_ok=True);children=[];streams=[];checked=False
    for i in range(a.workers):
        rank=a.node*a.workers+i;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream);children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--kind',a.kind,'--rank',str(rank),'--workers',str(a.workers),'--threads','2'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        bad=[dict(rank=a.node*a.workers+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() is not None]
        if bad:atomic(VOUT/'failures'/f'semantic_{a.kind}_node{a.node}.json',dict(status='FAILED',time=stamp(),ranks=bad));raise RuntimeError(str(bad))
        if not checked and all((SEM/a.kind/f'smoke/rank{a.node*a.workers+i:03d}.json').exists() for i in range(a.workers)):
            atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),workers=a.workers,threads=2));checked=True
        time.sleep(10)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['node','worker']);p.add_argument('--kind',choices=['scan','rapid'],required=True);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);p.add_argument('--workers',type=int,default=8);p.add_argument('--threads',type=int,default=2);a=p.parse_args();globals()[a.mode](a)
