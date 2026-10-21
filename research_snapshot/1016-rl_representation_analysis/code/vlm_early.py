"""Prioritize the small action-interface cache while the full transpose continues.

Reads existing collection members only; no model rerun or frozen-file changes.
The early cells must later match the independently produced formal cells exactly.
"""
from common import *
import argparse
import numpy as np
from vlm_core import VOUT,LANGUAGE_GROUPS
from repair_queue_v2 import atomic_unique as atomic
EARLY=VOUT/'early_interface'

def extract():
    import psutil
    from vlm_pivot import save_array
    plan=read(VOUT/'PIVOT_PLAN.json');block=next(b for b in plan['blocks'] if b['name']=='interface_post');n=plan['expected_cases'];shape=block['shape'];need=n*int(np.prod(shape))*4
    assert psutil.virtual_memory().available>need*1.2+4*1024**3
    values=np.empty((n,*shape),dtype=np.float32);seen=np.zeros(n,dtype=bool);base=ROOT/'runs/vlm_all_layers_20261016_v1';sources=[]
    receipts=sorted((base/'receipts').glob('collect_*.json'));assert len(receipts)==6456
    for k,p in enumerate(receipts):
        receipt=read(p);result_path=base/'results'/p.name;assert sha(result_path)==receipt['result_sha256'];result=read(result_path)
        with np.load(ROOT/result['array_path']) as data:
            indices=data['global_indices'];assert not seen[indices].any();values[indices]=data['interface_post'];seen[indices]=True
        sources.append(dict(path=result['array_path'],sha256=result['array_sha256']))
        if k%256==0:atomic(EARLY/'EXTRACTION_PROGRESS.json',dict(time=stamp(),chunks=k+1,total=6456))
    assert seen.all()
    for j,group in enumerate(LANGUAGE_GROUPS):
        path=EARLY/'cells'/('interface_post__'+group+'.npy');v=values[:,j,:];h=save_array(path,v);valid=np.isfinite(v).all(1)
        assert (valid|np.isnan(v).all(1)).all()
        atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),cell='interface_post__'+group,block='interface_post',group=group,group_index=j,owner=0,path=str(path.relative_to(ROOT)),sha256=h,shape=list(v.shape),valid_cases=int(valid.sum()),missing_cases=int((~valid).sum()),early_priority=True,formal_equality_check_pending=True))
    atomic(EARLY/'EXTRACTION_COMPLETE.json',dict(status='PASS',time=stamp(),cases=n,cells=len(LANGUAGE_GROUPS),source_members_crc_checked=True,whole_source_hashes_assigned_to_formal_pivot=True,sources=sources,no_model_rerun=True))
    print('EARLY_INTERFACE_EXTRACT_PASS',flush=True)

def worker(args):
    import vlm_scan,vlm_scan_queue
    vlm_scan.VOUT=EARLY;vlm_scan_queue.VOUT=EARLY
    vlm_scan_queue.worker(args)

def node(args):
    import subprocess
    setup(f'vlm_repair/early/node{args.node}');execution=read(EARLY/'SCAN_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    folder=EARLY/f'scan/node{args.node}';folder.mkdir(parents=True,exist_ok=True);(EARLY/'scan/claims').mkdir(exist_ok=True)
    children=[];streams=[];checked=False
    for i in range(args.workers):
        rank=args.node*args.workers+i;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank),'--workers',str(args.workers),'--threads','2'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        bad=[p.returncode for p in children if p.poll() is not None]
        if bad:raise RuntimeError(str(bad))
        if not checked and all((EARLY/f'scan/smoke/rank{args.node*args.workers+i:03d}.json').exists() for i in range(args.workers)):
            atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),workers=args.workers));checked=True
        time.sleep(5)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['extract','worker','node']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);p.add_argument('--workers',type=int,default=8);p.add_argument('--threads',type=int,default=2);args=p.parse_args();setup('vlm_repair/early/setup');extract() if args.mode=='extract' else globals()[args.mode](args)
