"""Supplemental CPU workers claim only the already registered canonical-layer grids."""
from common import *
import argparse,subprocess,traceback
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def worker(args):
    setup(f'vlm_repair/core_scan/{args.rank}');from threadpoolctl import threadpool_limits
    limit=threadpool_limits(limits=2)
    from vlm_scan_queue import numeric_smoke
    from vlm_scan import scan
    numeric_smoke(args.rank);base=VOUT/'scan';done_count=0
    try:
        while True:
            tasks=read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical'];ready={p.stem for p in (VOUT/'cells').glob('*.json')};done={p.stem for p in (base/'receipts').glob('*.json')};claimed={p.name for p in (base/'claims').glob('*')};chosen=None
            for task in tasks:
                if task['id'] not in ready or task['id'] in done or task['id'] in claimed:continue
                directory=base/'claims'/task['id']
                try:directory.mkdir()
                except FileExistsError:continue
                atomic(directory/'OWNER.json',dict(rank=args.rank,pid=os.getpid(),time=stamp(),task=task,canonical_supplement=True));chosen=task;break
            status=base/'workers'/f'rank{args.rank:03d}.json'
            if chosen is None:atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=done_count,canonical_only=True));time.sleep(5);continue
            atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=chosen['id'],tasks_done=done_count,canonical_only=True));began=time.monotonic();result=scan(chosen['cell']);path=base/'results'/(chosen['id']+'.json')
            atomic(base/'receipts'/(chosen['id']+'.json'),dict(status='COMPLETE',time=stamp(),rank=args.rank,task=chosen,result_sha256=sha(path),seconds=time.monotonic()-began,canonical_supplement=True));done_count+=1
    except BaseException as error:
        atomic(VOUT/'failures'/f'core_scan_rank{args.rank}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'vlm_repair/core_scan/node{args.node}');p=read(VOUT/'CORE_SCAN_EXECUTION.json')
    for path,h in p['code_sha256'].items():assert sha(ROOT/path)==h,path
    folder=VOUT/f'core_scan/node{args.node}';folder.mkdir(parents=True,exist_ok=True);children=[];streams=[]
    for i in range(8):
        rank=32+args.node*8+i;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream);children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        failed=[dict(rank=32+args.node*8+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() is not None]
        if failed:atomic(VOUT/'failures'/f'core_scan_node{args.node}.json',dict(status='FAILED',time=stamp(),ranks=failed));raise RuntimeError(str(failed))
        time.sleep(5)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);args=p.parse_args();globals()[args.mode](args)
