"""Independent analysis program, retained containers; no model or collection entrypoints."""
from common import *
import argparse
import subprocess
import traceback
import uuid
import numpy as np
from subspace_scan_prepare import OUT,name


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);assert path.resolve().is_relative_to(ROOT)
    for attempt in range(6):
        tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');tmp.replace(path);return
        except OSError:
            if attempt==5:raise
            time.sleep(min(.25*2**attempt,4))


_TASKS=[]
_CURSOR=0
_VERSION=None

def claim(base,rank):
    global _TASKS,_CURSOR,_VERSION
    version=(base/'tasks.json').stat().st_mtime_ns
    if version!=_VERSION:_TASKS=read(base/'tasks.json');_VERSION=version
    directory=base/'claims';directory.mkdir(parents=True,exist_ok=True)
    while _CURSOR<len(_TASKS):
        task=_TASKS[_CURSOR];_CURSOR+=1
        if (base/'receipts'/f'{task["id"]}.json').exists():continue
        try:(directory/task['id']).mkdir()
        except FileExistsError:continue
        write(directory/task['id']/'OWNER.json',dict(rank=rank,time=stamp(),task=task));return task
    return None


def smoke(backend,rank,base):
    from subspace_scan_math import directions
    from subspace_scan_cv import mul,endpoint
    rng=np.random.default_rng(20261016);proof=[]
    for route in ['r1','r2']:
        cell=name(route,-1 if route=='r1' else 0,4,6,0);x=np.load(OUT/'cache'/(cell+'.npy'),mmap_mode='r')
        if route=='r1':
            meta=read(OUT/'natural_metadata.json');q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');exp=np.array([r['subset']=='exploration' for r in meta])
            hi=np.array(x[np.flatnonzero(exp&(q>.9))[:80]],dtype=np.float64);lo=np.array(x[np.flatnonzero(exp&(q<.7))[:80]],dtype=np.float64)
        else:
            q=np.load(OUT/'cache/r2_a0_scores.npy');meta=read(OUT/'paired_metadata.json');mask=np.array([r['subset']=='exploration' for r in meta])&endpoint(q[0])
            idx=np.flatnonzero(mask)[:80];a=np.array(x[0,idx],dtype=np.float64);scores=q[0,idx];ii=np.arange(len(a))
            hi=a[ii,np.argmax(scores,axis=1)];lo=a[ii,np.argmin(scores,axis=1)]
        for centered in [False,True]:
            w,c,m=directions(hi,lo,centered,3);valid=np.flatnonzero(np.isfinite(w).all(0));w=w[:,valid]
            inputs=np.concatenate([hi[:16],lo[:16]])
            expected=mul(inputs,w,c,'cpu_float64');actual=mul(inputs,w,c,backend)
            diff=float(np.max(np.abs(expected-actual)));assert diff<1e-9,(backend,route,centered,diff)
            proof.append(dict(route=route,centered=centered,probes=len(valid),max_coordinate_difference=diff))
    result=dict(status='PASS',time=stamp(),rank=rank,backend=backend,real_existing_representations=True,model_loaded=False,checks=proof)
    write(base/'smoke'/f'rank{rank:03d}.json',result)


def worker(args):
    setup(f'subspace_scan/{args.run}/{args.rank}');compatibility()
    from subspace_scan_cv import scan
    base=ROOT/'runs'/args.run;status=base/'workers'/f'rank{args.rank:03d}.json';cfg=read(args.execution)
    from threadpoolctl import threadpool_limits,threadpool_info
    thread_controller=threadpool_limits(limits=cfg['cpu_threads_per_worker'])
    pools=threadpool_info()
    assert all(r['num_threads']==cfg['cpu_threads_per_worker'] for r in pools if r['user_api']=='blas')
    write(base/'runtime'/f'rank{args.rank:03d}.json',dict(time=stamp(),rank=args.rank,backend=cfg['score_backend'],cpu_threads_per_worker=cfg['cpu_threads_per_worker'],threadpools=pools,model_loaded=False))
    try:
        smoke(cfg['score_backend'],args.rank,base)
        node=args.rank//cfg['workers_per_node']
        while not (base/f'node{node}/SMOKE_PASS.json').exists():write(status,dict(status='WAIT_LOCAL_SMOKE',time=stamp()));time.sleep(2)
        count=0
        while True:
            task=claim(base,args.rank)
            if task is None:write(status,dict(status='QUEUE_WAIT',time=stamp(),tasks_done=count));time.sleep(5);continue
            write(status,dict(status='COMPUTING',time=stamp(),task=task['id'],tasks_done=count));began=time.monotonic()
            if task['phase']=='cv':doc=scan(task,cfg['score_backend'])
            else:
                from subspace_scan_confirm import confirm
                doc=confirm(task,cfg['score_backend'])
            dest=base/'results'/f'{task["id"]}.json';assert not dest.exists();write(dest,doc);count+=1
            write(base/'receipts'/f'{task["id"]}.json',dict(status='COMPLETE',time=stamp(),task=task,rank=args.rank,result_sha256=sha(dest),seconds=time.monotonic()-began))
            write(status,dict(status='RUNNING',time=stamp(),tasks_done=count,last_task=task['id']))
    except BaseException as e:
        write(base/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise


def node(args):
    setup(f'subspace_scan/{args.run}/node{args.node}');compatibility()
    from natural_coordinate import preflight
    execution=read(args.execution);preflight(args,execution);base=ROOT/'runs'/args.run;folder=base/f'node{args.node}'
    from subspace_scan_prepare import prepare,ensure_cache_index
    try:
        prepare(args.node)
        while not ensure_cache_index():
            write(folder/'STATUS.json',dict(status='WAIT_CACHE_INDEX',time=stamp(),node=args.node));time.sleep(5)
        children=[];streams=[]
        count=execution['workers_per_node']
        for local in range(count):
            rank=args.node*count+local;threads=str(execution['cpu_threads_per_worker']);env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local%16),OMP_NUM_THREADS=threads,MKL_NUM_THREADS=threads,OPENBLAS_NUM_THREADS=threads)
            for key in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(key,None)
            stream=(folder/f'rank{rank:03d}.log').open('x');streams.append(stream)
            children.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'worker','--rank',str(rank),'--run',args.run,'--execution',str(args.execution)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
        checked=False
        while True:
            failed=[(i+args.node*count,p.returncode) for i,p in enumerate(children) if p.poll() is not None]
            if failed:raise RuntimeError(f'Analysis workers exited: {failed}; original exceptions preserved')
            if not checked and all((base/'smoke'/f'rank{r:03d}.json').exists() for r in range(args.node*count,(args.node+1)*count)):
                write(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),workers=count,physical_devices=16,model_loaded=False));checked=True
            states=[read(p) for p in (base/'workers').glob('rank*.json') if int(p.stem[-3:])//count==args.node]
            write(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),node=args.node,smoke_pass=checked,tasks_done=sum(r.get('tasks_done',0) for r in states)))
            time.sleep(30)
    except BaseException as e:
        write(folder/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int,default=0);p.add_argument('--run',required=True);p.add_argument('--execution',required=True,type=Path);args=p.parse_args()
    if args.command=='node':node(args)
    else:worker(args)
