"""Independent native correction collector fills small-kernel GPU scheduling gaps.

The frozen inference workers and original gap collectors remain untouched. Every
new collector first exactly reproduces two committed 64-pool records, hidden
states, seeded baseline trajectories and independently scored PDM fields.
"""
from common import *
import argparse,subprocess,traceback
from repair_queue_v2 import atomic_unique as atomic
from vlm_semantic import SEM

def worker(a):
    setup(f'vlm_semantic_v2/overlap/rank{a.rank:03d}');compatibility()
    import numpy as np
    import torch
    import vlm_semantic_collect as collection
    Original=collection.SemanticRuntime
    class Verified(Original):
        def __init__(self):
            super().__init__()
            from worker import load_features,predict
            from repair_engine import baseline_row
            from repair_score import score_group
            protocol=read(SEM/'OVERLAP_EXECUTION.json');ref=read(ROOT/protocol['reference_result']);assert sha(ROOT/ref['array_path'])==ref['array_sha256']
            panel=read(collection.BASE/'panel.json');lookup={r['token']:r for r in panel};checks=[]
            with np.load(ROOT/ref['array_path']) as data,torch.no_grad():
                for i,record in enumerate(ref['records'][:2]):
                    row=lookup[record['token']];h,pools,bounds=self.forward_semantic(collection.raw_features(row));assert set(pools)==set(data.files)-{'global_indices'}
                    for name,value in pools.items():assert np.array_equal(value,data[name][i]),name
                    cached,_,_=load_features(row,self.cfg);assert torch.equal(h[0].cpu(),cached['last_hidden_state'])
                    b=baseline_row(row);pred=predict(self.agent,dict(cached,last_hidden_state=h[0].cpu()),seed(row['token']));assert np.array_equal(pred,b['trajectory'])
                    actual=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=self.cfg['scoring'],records=[dict(arm='baseline',trajectory=pred.tolist())]))[0]['score'];assert actual==b['score']
                    checks.append(dict(token=row['token'],all_64_pools_exact=True,native_hidden_exact=True,seeded_trajectory_and_seven_scores_exact=True))
            self.verify_weights();atomic(SEM/f'overlap/smoke/rank{a.rank:03d}.json',dict(status='PASS',time=stamp(),rank=a.rank,checks=checks))
    # Scheduling policy only. The original module, forward, pooling, claim,
    # storage and deterministic reference physics retain their frozen hashes.
    collection.SemanticRuntime=Verified;collection.idle=lambda rank:True
    collection.worker(a)

def node(a):
    setup(f'vlm_semantic_v2/overlap/node{a.node}')
    import torch,psutil
    assert torch.cuda.device_count()==16 and psutil.virtual_memory().available>128*1024**3
    execution=read(SEM/'OVERLAP_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    dest=SEM/f'overlap/node{a.node}';devices=[14,15];memory={i:torch.cuda.mem_get_info(i)[0] for i in devices};assert min(memory.values())>24*1024**3,memory
    atomic(dest/'PREFLIGHT.json',dict(status='PASS',time=stamp(),devices=devices,free_gpu_memory=memory,existing_frozen_workers_unchanged=True))
    children=[];streams=[]
    for local,device in enumerate(devices):
        rank=64+a.node*2+local;stream=(dest/f'rank{rank:03d}.log').open('a');streams.append(stream);env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(device))
        for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
        children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        bad=[dict(rank=64+a.node*2+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() not in [None,0]]
        if bad:atomic(SEM/f'overlap/failures/node{a.node}.json',dict(status='FAILED',time=stamp(),ranks=bad));raise RuntimeError(str(bad))
        if all(p.poll()==0 for p in children):atomic(dest/'COMPLETE.json',dict(status='PASS',time=stamp()));return
        atomic(dest/'STATUS.json',dict(status='RUNNING',time=stamp(),pids=[p.pid for p in children],devices=devices))
        time.sleep(20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);a=p.parse_args();globals()[a.mode](a)
