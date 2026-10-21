"""Task-private, appendable 32-worker queue for expanded-candidate causal repair tests."""
from common import *
import argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import subprocess
import traceback
from functools import lru_cache
from repair_queue_v2 import claim,append,stage,atomic_unique,init_score_unique
atomic=atomic_unique

@lru_cache(maxsize=16)
def inputs(path):
    path=Path(path);p=read(path/'PROTOCOL.json')
    assert sha(path/'panel.json')==p['panel_sha256'] and sha(path/'arms.json')==p['arms_sha256']
    return read(path/'panel.json'),read(path/'arms.json')

class Dispatch:
    def __init__(self,head):
        from candidate_repair_engine import CandidateEditor
        from repair_engine import Editor
        self.new=CandidateEditor(head);self.old=Editor(head)
    def predict(self,chain,arm):
        if arm['method']=='legacy':return self.old.predict(chain,arm['legacy_arm'])
        if arm['method']=='trajectory_scale':
            from repair_postprocess import scale_trajectory
            return scale_trajectory(chain['trajectory'],arm['factor']),dict(relative_edit_max=0.,relative_edit_l2_max=0.,gate_mean=1.)
        return self.new.predict(chain,arm)
    def close(self):self.new.close();self.old.close()

def score_inputs(row,cfg):
    from repair_test_features import load_features
    from repair_engine import baseline_row
    features,_,meta=load_features(row,cfg)
    before=dict(metric_sha256=row['metric_sha256'],feature_sha256=meta['feature_sha256']) if row.get('cohort')=='navtest' else baseline_row(row)
    assert meta['feature_sha256']==before['feature_sha256']
    return features,meta,before

def smoke(agent,editor,cfg,rank,base):
    import torch
    import numpy as np
    from repair_engine import trace,geometries
    from repair_score import score_group
    arms=read(ROOT/'candidate_repair_v1/smoke_arms.json');checks=[]
    for row in read(ROOT/'repair_v1/anchors.json'):
        features,meta,b=score_inputs(row,cfg)
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']));assert np.array_equal(chain['trajectory'],b['trajectory'])
            output=[dict(arm='baseline',trajectory=chain['trajectory'].tolist())]
            for arm in arms:
                pred,edit=editor.predict(chain,arm);again,_=editor.predict(chain,arm);assert np.array_equal(pred,again)
                zero,_=editor.predict(chain,dict(arm,alpha=0.));assert np.array_equal(zero,chain['trajectory'])
                full,_=editor.predict(chain,dict(arm,from_start=True));assert np.array_equal(full,pred)
                output.append(dict(arm=arm['id'],trajectory=pred.tolist(),edit=edit,geometry=geometries(pred,chain['trajectory'])))
        task=dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=output)
        scores=score_group(task);reverse=score_group(dict(task,records=list(reversed(output))))
        assert [r['score'] for r in scores]==[r['score'] for r in reversed(reverse)]
        assert scores[0]['score']==b['score']
        checks.append(dict(token=row['token'],feature_sha256=meta['feature_sha256'],records=scores))
    proof=dict(status='PASS',time=stamp(),rank=rank,records=checks,identity_exact=True,native_prefix_exact=True,score_order_invariant=True)
    atomic(base/'smoke'/f'rank{rank:03d}.json',proof)
    return proof

def run_task(agent,editor,cfg,task,base,pool):
    import numpy as np
    import torch
    from repair_engine import trace,geometries
    from repair_score import score_group
    panel,arms=inputs(str(base/'stages'/task['stage']));pending=[];records=[]
    for row in panel[task['start']:task['end']]:
        features,meta,b=score_inputs(row,cfg)
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token'],task['seed_index']))
            if task['seed_index']==0 and row.get('cohort')!='navtest':assert np.array_equal(chain['trajectory'],b['trajectory'])
            candidates=[dict(arm='baseline',trajectory=chain['trajectory'].tolist(),edit=dict(relative_edit_max=0.,relative_edit_l2_max=0.))]
            for arm in arms:
                pred,edit=editor.predict(chain,arm)
                assert np.isfinite(pred).all()
                candidates.append(dict(arm=arm['id'],trajectory=pred.tolist(),edit=edit,geometry=geometries(pred,chain['trajectory'])))
        pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=candidates)),row,meta,b))
    for future,row,meta,b in pending:
        output=future.result(timeout=1800)
        if task['seed_index']==0 and row.get('cohort')!='navtest':assert output[0]['score']==b['score']
        for r in output:r.update(token=row['token'],session=row['session'],subset=row['subset'],original_S0_quality=row['quality'],
            seed_index=task['seed_index'],seed=seed(row['token'],task['seed_index']),feature_sha256=meta['feature_sha256'],metric_sha256=b['metric_sha256'])
        records.extend(output)
    return records

def worker(args):
    setup(f'candidate_repair/{args.run}/rank{args.rank:03d}');compatibility()
    import torch
    from worker import load_model
    base=ROOT/'runs'/args.run;status=base/'workers'/f'rank{args.rank:03d}.json'
    try:
        cfg=read(ROOT/'configs/repair_final_baseline.json');agent,runtime=load_model(cfg);versions={k:p._version for k,p in agent.named_parameters()}
        editor=Dispatch(agent.action_head);atomic(base/'workers'/f'rank{args.rank:03d}_runtime.json',runtime)
        smoke(agent,editor,cfg,args.rank,base)
        if args.dsw:
            editor.close();assert versions=={k:p._version for k,p in agent.named_parameters()};return
        while not (base/f'node{args.rank//16}/SMOKE_PASS.json').exists():
            atomic(status,dict(status='WAIT_LOCAL_SMOKE',time=stamp(),rank=args.rank));time.sleep(2)
        done=0;start=time.monotonic()
        with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
            while True:
                task=claim(base,args.rank)
                if task=='CLOSED':break
                if task is None:
                    atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=done));time.sleep(5);continue
                atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id'],tasks_done=done))
                p=base/'results'/(task['id']+'.json');assert not p.exists()
                rows=run_task(agent,editor,cfg,task,base,pool)
                atomic(p,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=rows))
                atomic(base/'receipts'/p.name,dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=len(rows),result_sha256=sha(p)))
                done+=1;atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=done,seconds=time.monotonic()-start,last_result=str(p)))
                assert versions=={k:p._version for k,p in agent.named_parameters()}
        editor.close();assert all(p.grad is None for p in agent.parameters())
        atomic(status,dict(status='COMPLETE',time=stamp(),rank=args.rank,tasks_done=done,base_unchanged=True))
    except BaseException as error:
        atomic(base/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'candidate_repair/{args.run}/node{args.node}');compatibility()
    from natural_coordinate import preflight
    execution=read(args.execution);preflight(args,execution)
    for p,h in execution['fit_sha256'].items():assert sha(ROOT/p)==h
    base=ROOT/'runs'/args.run;folder=base/f'node{args.node}';children=[];streams=[];checked=False;start=time.monotonic();last_check=start
    try:
        for local in range(16):
            rank=args.node*16+local;s=(folder/f'rank{rank:03d}.log').open('a');streams.append(s)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
            children.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'worker','--run',args.run,'--rank',str(rank)],cwd=ROOT,env=env,stdout=s,stderr=subprocess.STDOUT))
        while True:
            failed=[dict(rank=args.node*16+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() not in (None,0)]
            if failed:raise RuntimeError(f'Failed ranks {failed}; original worker exceptions retained')
            if not checked and all((base/'smoke'/f'rank{r:03d}.json').exists() for r in range(args.node*16,(args.node+1)*16)):
                reference=read(ROOT/execution['dsw_reference'])['records']
                for rank in range(args.node*16,(args.node+1)*16):assert read(base/'smoke'/f'rank{rank:03d}.json')['records']==reference
                atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=16,exact_DSW=True));checked=True
            states=[]
            for rank in range(args.node*16,(args.node+1)*16):
                p=base/'workers'/f'rank{rank:03d}.json'
                if p.exists():states.append(read(p))
            status=dict(status='RUNNING',time=stamp(),node=args.node,smoke_pass=checked,tasks_done=sum(s.get('tasks_done',0) for s in states),workers=len(states),seconds=time.monotonic()-start)
            atomic(folder/'STATUS.json',status);print(json.dumps(status),flush=True)
            if time.monotonic()-last_check>=300:
                samples=[read(s['last_result']) for s in states if s.get('last_result')]
                for doc in samples:
                    for r in doc['records']:
                        assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(r['score']['score'])
                        assert len(r['trajectory'])==8 and all(len(p)==3 for p in r['trajectory'])
                        assert 0<=r['score']['score']<=1
                atomic(folder/f'SEMANTIC_{int(time.monotonic()-start):06d}.json',dict(status='PASS',time=stamp(),records=sum(len(s['records']) for s in samples),checks=['seed','shape','score','quality','parameter_versions_each_task']))
                last_check=time.monotonic()
            if all(p.poll() is not None for p in children):break
            time.sleep(30)
        atomic(folder/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),exit_codes=[p.returncode for p in children]))
    except BaseException as error:
        atomic(folder/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for s in streams:s.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','node']);p.add_argument('--run',required=True);p.add_argument('--rank',type=int,default=0)
    p.add_argument('--node',type=int);p.add_argument('--execution',type=Path);p.add_argument('--dsw',action='store_true');a=p.parse_args()
    worker(a) if a.command=='worker' else node(a)
