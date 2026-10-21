"""Append-only upstream repair queue: CPU input prefetch, reusable VLM prefixes and seed conditions."""
from common import *
import argparse
import multiprocessing as mp
import subprocess
import traceback
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor
from repair_queue_v2 import claim,append,atomic_unique as atomic,init_score_unique
from vlm_core import VOUT,raw_features
from vlm_intervene import Engine

@lru_cache(maxsize=12)
def inputs(path):
    p=Path(path);protocol=read(p/'PROTOCOL.json');assert sha(p/'panel.json')==protocol['panel_sha256'] and sha(p/'arms.json')==protocol['arms_sha256']
    return read(p/'panel.json'),read(p/'arms.json')

def stage(base,name,panel,arms,seeds,chunk=2,arm_chunk=64):
    dest=base/'stages'/name;assert not (dest/'PROTOCOL.json').exists();atomic(dest/'panel.json',panel);atomic(dest/'arms.json',arms)
    tasks=[dict(id=f'{name}_a{a:05d}_{i:06d}',stage=name,start=i,end=min(i+chunk,len(panel)),arm_start=a,arm_end=min(a+arm_chunk,len(arms)),seeds=seeds)
           for a in range(0,len(arms),arm_chunk) for i in range(0,len(panel),chunk)]
    atomic(dest/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),scenes=len(panel),arms=len(arms),seeds=seeds,tasks=len(tasks),panel_sha256=sha(dest/'panel.json'),arms_sha256=sha(dest/'arms.json'),native_vlm_reused_across_seeds=True,baseline_repeated_per_arm_chunk=True))
    append(base,tasks);return len(tasks)

class Fits:
    def __init__(self):self.cache={}
    def get(self,arm):
        import torch
        import numpy as np
        p=arm['fit_path']
        if p not in self.cache:
            assert sha(ROOT/p)==arm['fit_sha256']
            with np.load(ROOT/p) as f:self.cache[p]={k:torch.as_tensor(np.array(f[k]),device='cuda',dtype=torch.float32) for k in f.files}
        return self.cache[p]

def read_case(row):
    began=time.monotonic();features=raw_features(row)
    from repair_engine import baseline_row
    before=dict(metric_sha256=row['metric_sha256']) if row.get('cohort')=='navtest' else baseline_row(row)
    return features,before,time.monotonic()-began

def run_task(e,fits,task,base,pool,prefetch=True):
    import torch
    import numpy as np
    from repair_score import score_group
    from repair_engine import geometries
    panel,all_arms=inputs(str(base/'stages'/task['stage']));rows=panel[task['start']:task['end']];arms=all_arms[task['arm_start']:task['arm_end']]
    pending=[];out=[];timing=dict(read_decode_cpu_seconds=0.,input_wait_seconds=0.,gpu_submit_seconds=0.,device_return_wall_seconds=0.,scoring_wait_seconds=0.)
    with ThreadPoolExecutor(max_workers=1) as reader:
        next_input=reader.submit(read_case,rows[0]) if prefetch and rows else None
        for i,row in enumerate(rows):
            started=time.monotonic();features,before,read_seconds=next_input.result() if prefetch else read_case(row);timing['input_wait_seconds']+=time.monotonic()-started;timing['read_decode_cpu_seconds']+=read_seconds
            if prefetch and i+1<len(rows):next_input=reader.submit(read_case,rows[i+1])
            preds=[];edits=[];labels=[];start=time.monotonic()
            with torch.no_grad():
                hidden=e.forward_native(features)
                baseline=[e.trajectory(features,hidden,seed(row['token'],j)) for j in task['seeds']]
                for j,p in zip(task['seeds'],baseline):preds.append(p);labels.append(('baseline',j));edits.append(p.new_zeros(4))
                for arm in arms:
                    if arm['method']=='combination':condition,interface,stat=e.combined(arm['parts'],fits.get)
                    else:
                        changed,stat=e.edited(arm,fits.get(arm));condition,interface=e.suffix(arm['block'],changed)
                    for j in task['seeds']:
                        preds.append(e.trajectory(features,condition,seed(row['token'],j),interface));labels.append((arm['id'],j));edits.append(stat)
                timing['gpu_submit_seconds']+=time.monotonic()-start;start=time.monotonic()
                # Two small batched transfers replace one synchronization per arm/metric.
                predictions=torch.stack(preds).float().cpu().numpy();stats=torch.stack(edits).float().cpu().numpy()
                timing['device_return_wall_seconds']+=time.monotonic()-start
            assert np.isfinite(predictions).all() and np.isfinite(stats).all();base_map={j:p for p,(a,j) in zip(predictions,labels) if a=='baseline'}
            if row.get('cohort')!='navtest' and 0 in base_map:assert np.array_equal(base_map[0],before['trajectory']),row['token']
            arm_map={a['id']:a for a in arms};records=[]
            for pred,stat,(ident,j) in zip(predictions,stats,labels):
                relative=float(stat[0]/max(stat[1],1e-12));assert relative<=(arm_map[ident]['cap']+1e-6 if ident!='baseline' else 1e-6)
                records.append(dict(arm=ident,trajectory=pred.tolist(),seed_index=j,seed=seed(row['token'],j),edit=dict(edit_norm=float(stat[0]),group_norm=float(stat[1]),relative_edit_max=relative,gate_mean=float(stat[2]),cap_factor=float(stat[3])),geometry=geometries(pred,base_map[j])))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=before['metric_sha256'],scoring=e.cfg['scoring'],records=records)),row,before))
    for future,row,before in pending:
        start=time.monotonic();records=future.result(timeout=1800);timing['scoring_wait_seconds']+=time.monotonic()-start
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0 and row.get('cohort')!='navtest':assert record['score']==before['score']
            record.update(token=row['token'],session=row['session'],subset=row['subset'],original_S0_quality=row.get('quality'),metric_sha256=before['metric_sha256'])
        out.extend(records)
    e.verify_engine();return out,timing

def smoke(e,rank,base):
    import torch
    import numpy as np
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    records=[]
    with torch.no_grad():
        for row in read(ROOT/'repair_v1/anchors.json')[:2]:
            raw=raw_features(row);cached,_,_=load_features(row,e.cfg);h=e.forward_native(raw);assert torch.equal(h[0].cpu(),cached['last_hidden_state']);b=baseline_row(row)
            basepred=e.trajectory(raw,h,seed(row['token']));assert np.array_equal(basepred.cpu().numpy(),b['trajectory'])
            zero=[]
            for block in e.prefix:
                hh,post=e.suffix(block,e.prefix[block]);assert torch.equal(hh,h),block
                if post is not None:assert torch.equal(e.trajectory(raw,hh,seed(row['token']),post),basepred)
                zero.append(block)
            scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=e.cfg['scoring'],records=[dict(arm='baseline',trajectory=basepred.cpu().numpy().tolist())]))
            assert scored[0]['score']==b['score'];records.append(dict(token=row['token'],zero_sites=zero,records=scored))
    e.verify_engine();result=dict(status='PASS',time=stamp(),rank=rank,records=records,all_62_zero_suffixes_exact=True,native_cached_hidden_exact=True)
    atomic(base/'smoke'/f'rank{rank:03d}.json',result);return result

def worker(args):
    setup(f'vlm_repair/{args.run}/rank{args.rank:03d}');compatibility();base=ROOT/'runs'/args.run;status=base/'workers'/f'rank{args.rank:03d}.json'
    try:
        e=Engine();fits=Fits();versions={k:p._version for k,p in e.agent.named_parameters()};smoke(e,args.rank,base)
        if args.dsw:return
        while not (base/f'node{args.rank//args.workers}/SMOKE_PASS.json').exists():time.sleep(2)
        done=0
        with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
            while True:
                task=claim(base,args.rank)
                if task=='CLOSED':raise RuntimeError('Retention protocol forbids a closed queue')
                if task is None:atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=done));time.sleep(5);continue
                atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id'],tasks_done=done));began=time.monotonic()
                records,timing=run_task(e,fits,task,base,pool);p=base/'results'/(task['id']+'.json');assert not p.exists();start=time.monotonic()
                atomic(p,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=records,timing=timing));write_seconds=time.monotonic()-start
                atomic(base/'receipts'/p.name,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=len(records),seconds=time.monotonic()-began,write_seconds=write_seconds,result_sha256=sha(p)))
                done+=1;atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=done,last_result=str(p)));assert versions=={k:p._version for k,p in e.agent.named_parameters()}
    except BaseException as error:
        atomic(base/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'vlm_repair/{args.run}/node{args.node}');base=ROOT/'runs'/args.run;execution=read(VOUT/'REPAIR_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    from natural_coordinate import preflight
    preflight(args,execution);folder=base/f'node{args.node}';folder.mkdir(parents=True,exist_ok=True);children=[];streams=[];checked=False
    for i in range(args.workers):
        rank=args.node*args.workers+i;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream);env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(i),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
        for key in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(key,None)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--run',args.run,'--rank',str(rank),'--workers',str(args.workers)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
    try:
        while True:
            failures=[dict(rank=args.node*args.workers+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() is not None]
            if failures:raise RuntimeError(str(failures))
            if not checked and all((base/f'smoke/rank{r:03d}.json').exists() for r in range(args.node*args.workers,(args.node+1)*args.workers)):
                reference=read(ROOT/execution['dsw_reference'])['records']
                for r in range(args.node*args.workers,(args.node+1)*args.workers):assert read(base/f'smoke/rank{r:03d}.json')['records']==reference
                atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),cards=args.workers,exact_DSW=True));checked=True
            time.sleep(5)
    except BaseException as error:
        atomic(base/'failures'/f'node{args.node}.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['worker','node']);p.add_argument('--run',required=True);p.add_argument('--rank',type=int,default=0);p.add_argument('--node',type=int);p.add_argument('--workers',type=int,default=16);p.add_argument('--dsw',action='store_true');a=p.parse_args();globals()[a.mode](a)
