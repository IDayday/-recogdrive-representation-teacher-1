"""Audit actual new-card outputs after five minutes on the shared queue."""
from common import *
import argparse,socket
import numpy as np
from vlm_elastic_registry import DEST,BASE,configuration
from vlm_clone_watch_v2 import resolved
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];lease=read(folder/'ADOPTED_CLONE.json')
    assert socket.gethostname().startswith(lease['job']);ranks=set(c['gpu_ranks'])
    while not (folder/'GPU_ENABLED.json').exists():time.sleep(5)
    enabled=read(folder/'GPU_ENABLED.json');started=dt.datetime.fromisoformat(enabled['time'])
    while (dt.datetime.now(dt.timezone.utc)-started).total_seconds()<300:time.sleep(5)
    while True:
        bad=[]
        for sub in ['failures','clone_wrapper_failures','command_failures']:
            bad += [p for p in (folder/sub).glob('*.json') if not resolved(p)]
        assert not bad,bad
        latest={}
        for p in (BASE/'receipts').glob('*.json'):
            if p.stat().st_mtime<started.timestamp()-2:continue
            r=read(p);rank=r['rank']
            if rank not in ranks:continue
            if rank not in latest or r['time']>latest[rank][1]['time']:latest[rank]=(p,r)
        if set(latest)==ranks:break
        print('WAIT_NEW_GPU_OUTPUT_COVERAGE',a.id,len(latest),len(ranks),flush=True);time.sleep(30)
    checks=[];arms_cache={}
    for rank,(p,r) in sorted(latest.items()):
        assert r['elastic_node']==a.id and r['elastic_config_sha256']==sha(folder/'CONFIG.json')
        path=BASE/'results'/p.name;assert sha(path)==r['result_sha256'];doc=read(path)
        assert doc['rank']==rank and doc['task']==r['task']
        owner=read(BASE/'claims'/r['task']['id']/'OWNER.json')
        assert owner['rank']==rank and owner['elastic_node']==a.id
        stage=doc['task']['stage']
        if stage not in arms_cache:arms_cache[stage]={x['id']:x for x in read(BASE/'stages'/stage/'arms.json')}
        for v in doc['records']:
            assert v['seed']==seed(v['token'],v['seed_index']) and v['quality']==quality(v['score']['score'])
            assert np.asarray(v['trajectory']).shape==(8,3) and np.isfinite(v['trajectory']).all()
            assert all(np.isfinite(x) and 0<=x<=1+1e-8 for x in v['score'].values())
            assert v['edit']['relative_edit_max']<=arms_cache[stage].get(v['arm'],{}).get('cap',0)+1e-6
        checks.append(dict(rank=rank,receipt=str(p.relative_to(ROOT)),result_sha256=r['result_sha256'],
            stage=stage,records=len(doc['records']),task_seconds=r['seconds']))
    atomic(folder/'GPU_QUEUE_FIVE_MINUTE_CHECK.json',dict(status='PASS',time=stamp(),node=a.id,job=lease['job'],
        elapsed_since_gpu_enable_seconds=(dt.datetime.now(dt.timezone.utc)-started).total_seconds(),
        actual_ranks=sorted(latest),all_configured_cards_produced_scientific_results=True,
        checks=checks,immutable_config_sha256=sha(folder/'CONFIG.json'),
        seeds_scores_trajectory_shapes_qualities_and_caps_verified=True,
        unchanged_frozen_model_scoring_and_queue_ownership=True,checker_sha256=sha(Path(__file__))))
    print('NEW_GPU_QUEUE_FIVE_MINUTE_CHECK_PASS',a.id,len(latest),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);main(p.parse_args())
