"""Independent correction queue; DSW contributes continuously and DLC fills idle GPU gaps."""
from common import *
import argparse,traceback
import numpy as np
from vlm_semantic import SEM,SemanticRuntime,GROUPS
from vlm_core import raw_features
from vlm_scan import save_npz
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_semantic_20261016_v2'

def prepare_tasks():
    rows=read(ROOT/'runs/vlm_all_layers_20261016_v1/panel.json');assert len(rows)==103288
    atomic(BASE/'panel.json',rows);tasks=[dict(id=f'semantic_{i:06d}',start=i,end=min(i+16,len(rows))) for i in range(0,len(rows),16)];atomic(BASE/'tasks.json',tasks);(BASE/'claims').mkdir(exist_ok=True)
    atomic(BASE/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),cases=len(rows),tasks=len(tasks),blocks=32,groups=GROUPS,cells=64,source='same frozen RL policy VLM, same raw observation, no action or GT fed to VLM',parent_collection='vlm_all_layers_20261016_v1',correction='BPE anchor excludes colon because colon is fused with newline',old_outputs_preserved=True))

def idle(rank):
    if rank==32:return True
    for run in ['vlm_repair_20261016_v2','vlm_global_refine_20261016_v5','vlm_final_test_20261017_v1']:
        p=ROOT/'runs'/run/'workers'/f'rank{rank:03d}.json'
        if p.exists() and read(p)['status']!='QUEUE_WAIT':return False
    return True

def worker(args):
    setup(f'vlm_semantic_v2/rank{args.rank:03d}');compatibility()
    import torch
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    expected=read(SEM/'EXECUTION.json')
    for p,h in expected['code_sha256'].items():assert sha(ROOT/p)==h,p
    e=SemanticRuntime();rows=read(BASE/'panel.json');tasks=read(BASE/'tasks.json');status=BASE/'workers'/f'rank{args.rank:03d}.json';completed=0;cursor=0
    try:
        # Actual cache/native validation on each assigned device before any formal collection.
        from worker import load_features
        with torch.no_grad():
            for row in read(ROOT/'repair_v1/anchors.json')[:2]:
                hidden,values,boundaries=e.forward_semantic(raw_features(row));cached,_,_=load_features(row,e.cfg);assert torch.equal(hidden[0].cpu(),cached['last_hidden_state'])
        atomic(BASE/'smoke'/f'rank{args.rank:03d}.json',dict(status='PASS',time=stamp(),rank=args.rank,native_cache_exact=True,all_corrected_regions_present=True))
        while True:
            if len(list((BASE/'receipts').glob('*.json')))==len(tasks):
                atomic(status,dict(status='COMPLETE',time=stamp(),rank=args.rank,tasks_done=completed));return
            if not idle(args.rank):atomic(status,dict(status='WAIT_SHARED_GPU',time=stamp(),rank=args.rank,tasks_done=completed));time.sleep(3);continue
            chosen=None
            while cursor<len(tasks):
                task=tasks[cursor];cursor+=1
                if (BASE/'receipts'/(task['id']+'.json')).exists():continue
                directory=BASE/'claims'/task['id']
                try:directory.mkdir()
                except FileExistsError:continue
                atomic(directory/'OWNER.json',dict(time=stamp(),rank=args.rank,pid=os.getpid(),task=task));chosen=task;break
            if chosen is None:cursor=0;time.sleep(5);continue
            atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=chosen['id'],tasks_done=completed));values=[];records=[]
            with torch.no_grad():
                for row in rows[chosen['start']:chosen['end']]:
                    while not idle(args.rank):atomic(status,dict(status='WAIT_SHARED_GPU',time=stamp(),rank=args.rank,task=chosen['id'],tasks_done=completed));time.sleep(3)
                    hidden,pools,bounds=e.forward_semantic(raw_features(row));values.append(pools);records.append(dict(token=row['token'],global_index=row['global_index'],boundaries=bounds));e.verify_weights()
            arrays={name:np.stack([v[name] for v in values]) for name in values[0]};arrays['global_indices']=np.array([r['global_index'] for r in records],dtype=np.int64)
            path=BASE/'arrays'/(chosen['id']+'.npz');hashed=save_npz(path,**arrays);result=BASE/'results'/(chosen['id']+'.json');atomic(result,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=chosen,array_path=str(path.relative_to(ROOT)),array_sha256=hashed,records=records))
            atomic(BASE/'receipts'/result.name,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=chosen,result_sha256=sha(result)));completed+=1
            atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=completed))
    except BaseException as error:
        atomic(BASE/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    import subprocess
    setup(f'vlm_semantic_v2/node{args.node}');folder=BASE/f'node{args.node}';folder.mkdir(parents=True,exist_ok=True);streams=[];children=[]
    for local in range(16):
        rank=args.node*16+local;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream);env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
        for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        bad=[dict(rank=args.node*16+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() not in [None,0]]
        if bad:atomic(BASE/'failures'/f'node{args.node}.json',dict(status='FAILED',time=stamp(),ranks=bad));raise RuntimeError(str(bad))
        if all(p.poll()==0 for p in children):atomic(folder/'COMPLETE.json',dict(status='PASS',time=stamp()));return
        time.sleep(10)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','worker','node']);p.add_argument('--rank',type=int);p.add_argument('--node',type=int);args=p.parse_args();setup('vlm_semantic_v2/setup');prepare_tasks() if args.mode=='prepare' else globals()[args.mode](args)
