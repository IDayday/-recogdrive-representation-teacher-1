"""CPU session-CV workers overlap model work and prefer locally written cells."""
from common import *
import argparse
import subprocess
import traceback
import numpy as np
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT

def prepare():
    from vlm_rapid_space import configs,directions,metrics
    plan=read(VOUT/'PIVOT_PLAN.json');tasks=[]
    for block in plan['blocks']:
        for group in block['groups']:tasks.append(dict(id=block['name']+'__'+group,cell=block['name']+'__'+group,owner=block['owner'],block=block['name']))
    base=VOUT/'rapid';assert not (base/'tasks.json').exists();atomic(base/'tasks.json',tasks);atomic(base/'CONFIGS.json',configs())
    x=np.load(VOUT/'pivot_smoke/cells/language_norm__last_token.npy')[:,:64].astype(np.float64)
    hi=x[::2];lo=x[1::2];mom=[(len(a),a.sum(0),a.T@a) for a in [hi,lo]]
    w,c,status,rank,deg=directions(mom,True,123);good=np.flatnonzero((status==0)&~deg);assert len(good)
    pred=(x-c)@w[:,good];y=np.arange(len(x))%2==1;sessions=np.array(['engineering'+str(i%7) for i in range(len(x))]);m=metrics(pred,y,sessions,high_population=128)
    from vlm_rapid import save_npz
    ref=base/'numeric_reference.npz';save_npz(ref,x=x,w=w[:,good],center=c,indices=good,metrics=m)
    atomic(base/'NUMERIC_REFERENCE.json',dict(status='PASS',time=stamp(),reference_sha256=sha(ref),synthetic_balanced_engineering_labels=True,real_latent_input=True))
    atomic(base/'PROTOCOL.json',dict(status='FROZEN_BEFORE_SCAN',time=stamp(),tasks=len(tasks),configs=len(configs()),nominal_centered_variants=len(tasks)*len(configs())*2,
        folds=5,source_training_cases=103288,exploration_cases=85813,validation_cases=17475,exploration_only=True,
        fit='full valid exploration-class sufficient statistics in each training fold',evaluation='all valid S0 failures + up to 8192 uniform valid S0 highs, inverse-probability correction',
        constructions=['success PCA across full r grid','failure PCA across full r grid','3 random bases per r','full mean-gap'],
        nonlinear_controls=['full-energy score','success-PCA128 shrink-QDA'],
        preliminary_preservation='per cell, construction/equality/rank-band representatives; secondary S1/S2 scores on same held-out predictions; global/within-layer regions follow',
        multiplicity='exploratory BH and BY across all finite primary session p; confirm frozen regions with Holm in held-out sessions; no selection only from energy or p',
        role='fast all-cell preliminary readouts; full 11633-configuration residual grid remains queued separately, no claim of completed residual coverage',task_sha256=sha(base/'tasks.json'),configs_sha256=sha(base/'CONFIGS.json')))
    print(json.dumps(dict(status='PREPARED',cells=len(tasks),configs=len(configs()))),flush=True)

def numeric_smoke(rank):
    from vlm_rapid_space import directions,metrics
    path=VOUT/'rapid/numeric_reference.npz';assert sha(path)==read(VOUT/'rapid/NUMERIC_REFERENCE.json')['reference_sha256']
    with np.load(path) as a:
        x=np.array(a['x']);hi=x[::2];lo=x[1::2];mom=[(len(v),v.sum(0),v.T@v) for v in [hi,lo]]
        w,c,status,r,deg=directions(mom,True,123);indices=a['indices'];assert (status[indices]==0).all()
        assert np.allclose(w[:,indices],a['w'],rtol=1e-7,atol=1e-7)
        value=metrics((x-c)@w[:,indices],np.arange(len(x))%2==1,np.array(['engineering'+str(i%7) for i in range(len(x))]),high_population=128)
        assert np.allclose(value,a['metrics'],rtol=1e-7,atol=1e-7,equal_nan=True)
    atomic(VOUT/f'rapid/smoke/rank{rank:03d}.json',dict(status='PASS',time=stamp(),rank=rank,numeric_reference_exact_tolerance=1e-7,planner_loaded=False))

def claim(tasks,rank,workers):
    base=VOUT/'rapid';ready={p.stem for p in (VOUT/'cells').glob('*.json')};done={p.stem for p in (base/'receipts').glob('*.json')};claimed={p.name for p in (base/'claims').glob('*')}
    node=rank//workers
    dimensions={b['name']:b['shape'][1] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']}
    def priority(t):
        block=t['block'];group=t['cell'].split('__',1)[1]
        return (dimensions[block]>1536, group not in ['all_mean','last_token','patch_mean','image_mean','valid_mean','last8'],block!='interface_post',t['owner']!=node,dimensions[block],block)
    for task in sorted(tasks,key=priority):
        if task['cell'] not in ready or task['id'] in done or task['id'] in claimed:continue
        path=base/'claims'/task['id']
        try:path.mkdir()
        except FileExistsError:continue
        atomic(path/'OWNER.json',dict(rank=rank,pid=os.getpid(),time=stamp(),task=task));return task
    return None

def worker(args):
    setup(f'vlm_repair/rapid/rank{args.rank:03d}');from threadpoolctl import threadpool_limits
    limit=threadpool_limits(limits=args.threads);base=VOUT/'rapid';status=base/'workers'/f'rank{args.rank:03d}.json'
    try:
        numeric_smoke(args.rank)
        while not (base/f'node{args.rank//args.workers}/SMOKE_PASS.json').exists():time.sleep(2)
        tasks=read(base/'tasks.json');done=0
        from vlm_rapid import scan
        while True:
            task=claim(tasks,args.rank,args.workers)
            if task is None:
                atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=done));time.sleep(5);continue
            atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id'],tasks_done=done));began=time.monotonic()
            result=scan(task['cell']);path=base/'results'/(task['id']+'.json')
            atomic(base/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,result_sha256=sha(path),seconds=time.monotonic()-began))
            done+=1;atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=done,last_task=task['id']))
    except BaseException as error:
        atomic(VOUT/'failures'/f'rapid_rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'vlm_repair/rapid/node{args.node}');execution=read(VOUT/'RAPID_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    base=VOUT/'rapid';folder=base/f'node{args.node}';folder.mkdir(parents=True,exist_ok=True);(base/'claims').mkdir(exist_ok=True)
    processes=[];streams=[];checked=False
    for local in range(args.workers):
        rank=args.node*args.workers+local;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream)
        processes.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank),'--workers',str(args.workers),'--threads',str(args.threads)],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=stream,stderr=subprocess.STDOUT))
    while True:
        failures=[dict(rank=args.node*args.workers+i,returncode=p.returncode) for i,p in enumerate(processes) if p.poll() is not None]
        if failures:
            atomic(VOUT/'failures'/f'rapid_node{args.node}.json',dict(status='FAILED',time=stamp(),ranks=failures));raise RuntimeError(str(failures))
        if not checked and all((base/f'smoke/rank{args.node*args.workers+i:03d}.json').exists() for i in range(args.workers)):
            atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),workers=args.workers,threads_per_worker=args.threads));checked=True
        time.sleep(5)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);p.add_argument('--workers',type=int,default=16);p.add_argument('--threads',type=int,default=4)
    args=p.parse_args();setup('vlm_repair/rapid_setup');prepare() if args.mode=='prepare' else globals()[args.mode](args)
