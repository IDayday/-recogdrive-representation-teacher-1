"""Locked final test: UUID/mkdir scheduling, fresh matched RL baselines, optional action-scale control."""
from common import *
import argparse
import fcntl
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import subprocess
import traceback
from functools import lru_cache

@lru_cache(maxsize=12)
def stage_inputs(path):
    path=Path(path);return read(path/'panel.json'),read(path/'arms.json')

def atomic_unique(path,value):
    import uuid
    path=Path(path).resolve();assert path.is_relative_to(ROOT)
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    for attempt in range(6):
        tmp=path.with_name(path.name+'.'+str(os.getpid())+'.'+uuid.uuid4().hex+'.tmp')
        try:
            tmp.write_text(data);tmp.replace(path);return
        except OSError as e:
            if attempt==5:raise
            time.sleep(min(.25*2**attempt,4))

# PID values repeat across DLC containers. Every writer gets a globally unique temporary path.
atomic=atomic_unique
QUEUE_CURSOR=0
QUEUE_INDEX=None
QUEUE_VERSION=None

def init_score_unique():
    import socket
    setup(f'repair/scorer/{socket.gethostname()}/{os.getpid()}');compatibility()

def claim(base,rank):
    global QUEUE_CURSOR,QUEUE_INDEX,QUEUE_VERSION
    version=(base/'tasks.json').stat().st_mtime_ns
    if version!=QUEUE_VERSION:
        QUEUE_INDEX=read(base/'tasks.json');QUEUE_VERSION=version
    directory=base/'claims';directory.mkdir(parents=True,exist_ok=True)
    while QUEUE_CURSOR<len(QUEUE_INDEX):
        task=QUEUE_INDEX[QUEUE_CURSOR];QUEUE_CURSOR+=1
        if (base/'receipts'/f'{task["id"]}.json').exists():continue
        path=directory/task['id']
        try:path.mkdir()
        except FileExistsError:continue
        # mkdir is the sole cross-node ownership operation; no flock/counter read-modify-write.
        atomic(path/'OWNER.json',dict(task=task,rank=rank,pid=os.getpid(),time=stamp()))
        return task
    return 'CLOSED' if read(base/'queue.json')['closed'] else None

def append(base,tasks):
    base.mkdir(parents=True,exist_ok=True)
    with (base/'queue.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        old=read(base/'tasks.json') if (base/'tasks.json').exists() else []
        assert not set(t['id'] for t in old)&set(t['id'] for t in tasks)
        atomic(base/'tasks.json',old+tasks)
        if not (base/'queue.json').exists():atomic(base/'queue.json',dict(next=0,closed=False))

def stage(base,name,panel,arms,seeds,chunk=4):
    destination=base/'stages'/name;destination.mkdir(parents=True,exist_ok=True)
    assert not (destination/'PROTOCOL.json').exists()
    atomic(destination/'panel.json',panel);atomic(destination/'arms.json',arms)
    tasks=[dict(id=f'{name}_s{j}_{start:06d}',stage=name,start=start,end=min(start+chunk,len(panel)),seed_index=j)
           for j in seeds for start in range(0,len(panel),chunk)]
    atomic(destination/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),stage=name,scenes=len(panel),arms=len(arms),seeds=seeds,tasks=len(tasks),
        panel_sha256=sha(destination/'panel.json'),arms_sha256=sha(destination/'arms.json')))
    append(base,tasks);return len(tasks)

def smoke(agent,editor,cfg,rank,base):
    import torch
    import numpy as np
    from repair_test_features import load_features
    from repair_engine import trace,baseline_row,geometries
    from repair_score import score_group
    chosen=read(ROOT/'repair_v1/final_test_arms.json')
    identity_parent=next(a for a in chosen if a['method']!='trajectory_scale')
    records=[];versions={k:p._version for k,p in agent.named_parameters()}
    anchors=read(ROOT/'repair_v1/anchors.json')+read(base/'stages/final_test/panel.json')[:2]
    for row in anchors:
        features,gt,meta=load_features(row,cfg)
        b=(dict(metric_sha256=row['metric_sha256']) if row.get('cohort')=='navtest' else baseline_row(row))
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']))
            if row.get('cohort')!='navtest':assert np.array_equal(chain['trajectory'],b['trajectory'])
            identity=dict(identity_parent,alpha=0.)
            out,_=editor.predict(chain,identity);assert np.array_equal(out,chain['trajectory'])
            candidates=[dict(arm='identity',trajectory=out.tolist())]
            for a in chosen:
                if a['method']=='trajectory_scale':
                    from repair_postprocess import scale_trajectory
                    out=scale_trajectory(chain['trajectory'],a['factor']);again=scale_trajectory(chain['trajectory'],a['factor'])
                    metrics=dict(relative_edit_max=0.,gate_mean=1.)
                else:out,metrics=editor.predict(chain,a);again,_=editor.predict(chain,a)
                assert np.array_equal(out,again)
                assert metrics['relative_edit_max']<=a['cap']+1e-6
                candidates.append(dict(arm=a['id'],trajectory=out.tolist(),edit=metrics,geometry=geometries(out,chain['trajectory'])))
        scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=candidates))
        if row.get('cohort')!='navtest':assert scored[0]['score']==b['score']
        else:b['score']=scored[0]['score']
        records.append(dict(token=row['token'],records=scored,baseline=b['score'],feature_sha256=meta['feature_sha256']))
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    value=dict(status='PASS',time=stamp(),rank=rank,records=records,identity_exact=True,parameter_versions_checked=True)
    out=base/'smoke'/f'rank{rank:03d}.json';atomic(out,value)
    return value

def run_task(agent,editor,cfg,task,base,pool):
    import torch
    import numpy as np
    from repair_test_features import load_features
    from repair_engine import trace,baseline_row,geometries
    from repair_score import score_group
    stagepath=base/'stages'/task['stage'];panel,arms=stage_inputs(str(stagepath))
    pending=[];out=[]
    for row in panel[task['start']:task['end']]:
        features,_,meta=load_features(row,cfg)
        b=(dict(feature_sha256=meta['feature_sha256'],metric_sha256=row['metric_sha256']) if row.get('cohort')=='navtest' else baseline_row(row))
        assert meta['feature_sha256']==b['feature_sha256']
        reference_available=editor.set_reference(row['token']) if any(a['method'].startswith('patch') for a in arms) else False
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token'],task['seed_index']))
            if task['seed_index']==0 and row.get('cohort')!='navtest':assert np.array_equal(chain['trajectory'],b['trajectory']),row['token']
            candidates=[dict(arm='baseline',trajectory=chain['trajectory'].tolist(),edit=dict(relative_edit_max=0.))]
            memo={}
            for a in arms:
                key=dict(a);key.pop('id');key['method']='mean' if key['method']=='paired' else key['method'];key.pop('scope',None)
                key=digest(key)
                if key not in memo:
                    if a['method']=='trajectory_scale':
                        from repair_postprocess import scale_trajectory
                        memo[key]=(scale_trajectory(chain['trajectory'],a['factor']),dict(edit_norm=0.,relative_edit_max=0.,gate_mean=1.,cap_fraction=0.,sites=0))
                    else:memo[key]=editor.predict(chain,a)
                pred,metrics=memo[key]
                assert np.isfinite(pred).all() and metrics['relative_edit_max']<=a['cap']+1e-6
                candidates.append(dict(arm=a['id'],trajectory=pred.tolist(),edit=metrics,geometry=geometries(pred,chain['trajectory']),
                    reference_available=reference_available if a['method'].startswith('patch') else None))
        future=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=candidates))
        pending.append((future,row,meta,b))
    for future,row,meta,b in pending:
        records=future.result(timeout=1200)
        if task['seed_index']==0 and row.get('cohort')!='navtest':assert records[0]['score']==b['score']
        for r in records:r.update(token=row['token'],session=row['session'],subset=row['subset'],original_S0_quality=row['quality'],
            seed_index=task['seed_index'],seed=seed(row['token'],task['seed_index']),feature_sha256=meta['feature_sha256'],metric_sha256=b['metric_sha256'])
        out.extend(records)
    return out

def worker(args):
    setup(f'repair/{args.run}/rank{args.rank:03d}');compatibility()
    import torch
    from worker import load_model
    from repair_engine import Editor
    from score import init_scorer
    base=ROOT/'runs'/args.run;status=base/'workers'/f'rank{args.rank:03d}.json'
    try:
        cfg=read(ROOT/'configs/repair_final_baseline.json');agent,runtime=load_model(cfg);versions={k:p._version for k,p in agent.named_parameters()}
        editor=Editor(agent.action_head);atomic(base/'workers'/f'rank{args.rank:03d}_runtime.json',runtime)
        smoke(agent,editor,cfg,args.rank,base)
        node=args.rank//16
        if args.dsw:return
        while not (base/f'node{node}/SMOKE_PASS.json').exists():
            atomic(status,dict(status='WAIT_LOCAL_SMOKE',time=stamp(),rank=args.rank));time.sleep(2)
        done=0;began=time.monotonic()
        with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
            while True:
                task=claim(base,args.rank)
                if task=='CLOSED':break
                if task is None:
                    atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=done));time.sleep(5);continue
                atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id'],tasks_done=done))
                output=base/'results'/f'{task["id"]}.json'
                assert not output.exists()
                records=run_task(agent,editor,cfg,task,base,pool)
                atomic(output,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=records))
                done+=1
                atomic(base/'receipts'/f'{task["id"]}.json',dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,
                    records=len(records),result_sha256=sha(output)))
                atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=done,seconds=time.monotonic()-began,last_result=str(output)))
                assert versions=={k:p._version for k,p in agent.named_parameters()}
        editor.close();assert all(p.grad is None for p in agent.parameters())
        atomic(status,dict(status='COMPLETE',time=stamp(),rank=args.rank,tasks_done=done,base_unchanged=True))
    except BaseException as e:
        atomic(base/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(e),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'repair/{args.run}/node{args.node}');compatibility()
    from natural_coordinate import preflight
    execution=read(args.execution);preflight(args,execution)
    base=ROOT/'runs'/args.run;node=base/f'node{args.node}';children=[];streams=[];began=time.monotonic();checked=False
    try:
        for local in range(16):
            rank=args.node*16+local;out=node/f'rank{rank:03d}.log';stream=out.open('a');streams.append(stream)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
            children.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'worker','--run',args.run,'--rank',str(rank)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
        while True:
            failed=[(args.node*16+i,p.returncode) for i,p in enumerate(children) if p.poll() not in (None,0)]
            if failed:raise RuntimeError(f'Failed ranks {failed}; inspect preserved worker exceptions')
            if not checked and all((base/'smoke'/f'rank{r:03d}.json').exists() for r in range(args.node*16,(args.node+1)*16)):
                expected=read(ROOT/execution['dsw_reference'])['records'];tested=0
                for rank in range(args.node*16,(args.node+1)*16):
                    actual=read(base/'smoke'/f'rank{rank:03d}.json')['records'];assert actual==expected,(rank,'DLC/DSW smoke mismatch');tested+=len(actual)
                atomic(node/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=16,anchor_cases=tested,all_predictions_and_scores_exact_DSW=True));checked=True
            states=[read(base/'workers'/f'rank{r:03d}.json') for r in range(args.node*16,(args.node+1)*16) if (base/'workers'/f'rank{r:03d}.json').exists()]
            atomic(node/'STATUS.json',dict(status='RUNNING',time=stamp(),node=args.node,tasks_done=sum(r.get('tasks_done',0) for r in states),seconds=time.monotonic()-began,smoke_pass=checked))
            print(json.dumps(dict(node=args.node,workers=len(states),tasks_done=sum(r.get('tasks_done',0) for r in states),seconds=time.monotonic()-began,smoke_pass=checked)),flush=True)
            if all(p.poll() is not None for p in children):break
            time.sleep(30)
        atomic(node/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),node=args.node,exit_codes=[p.returncode for p in children]))
    except BaseException as e:
        atomic(node/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for stream in streams:stream.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','node']);p.add_argument('--run',required=True);p.add_argument('--rank',type=int,default=0)
    p.add_argument('--node',type=int);p.add_argument('--execution',type=Path);p.add_argument('--dsw',action='store_true');args=p.parse_args()
    if args.command=='worker':worker(args)
    else:node(args)
