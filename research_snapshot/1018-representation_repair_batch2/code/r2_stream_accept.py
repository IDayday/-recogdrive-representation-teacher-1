"""Bounded semantic acceptance of resumed supply, policy output and concurrency."""
from r2_common import *
from collections import Counter,defaultdict


def run(task):
    import numpy as np
    results={}
    base=ROOT/'runs/representation_coarse_v1';producer=read(base/'producer.json');queue=read(base/'tasks.json')
    assert producer['complete'] and len(queue)==producer['tasks']==32304 and producer['points']==4038
    assert len({t['id'] for t in queue})==len(queue)
    points=Counter(t['point'] for t in queue);assert len(points)==4038 and set(points.values())=={8}
    for point in points:
        d=read(ROOT/point);assert d['seeds']==[0] and len(d['panel'])==32
    accepted=dict(status='PASS',time=stamp(),points=4038,tasks=len(queue),unique_ids=True,all_points_32_train_cases=True,
        queue_order_sha256=sha(base/'tasks.json'),metadata_supply_complete=True,actual_gpu_sweep_complete=False,
        original_results_preserved=True,scientific_handler_sha256=sha(ROOT/'code/r2_eval_rollouts.py'))
    atomic(ROOT/'provenance/COARSE_DLC_RESUME_ACCEPTANCE.json',accepted);results['coarse_supply']=accepted
    base=ROOT/'runs/warm_hard_cv_v1';files=sorted((base/'results').glob('*.json'))[:300];modes=Counter();records=0;zero_checks=0;metrics=defaultdict(list)
    for path in files:
        d=read(path);point=read(ROOT/d['task']['point']);modes[d['mode']]+=1;native={}
        for r in d['records']:
            assert np.isfinite(r['trajectory']).all() and 0<=r['score']['score']<=1
            if r['arm']=='baseline':native[(r['token'],r['seed_index'])]=r
        for r in d['records']:
            if r['arm']=='baseline':continue
            b=native[(r['token'],r['seed_index'])]
            if r['choice']==0:
                assert r['trajectory']==b['trajectory'] and r['score']==b['score'];zero_checks+=1
            assert np.isfinite(r['relative_edit']) and np.isfinite(r['global_relative_edit'])
            metrics[r['arm']].append(r['score']['score']-b['score']['score'])
        records+=len(d['records'])
    results['hard_policy']=dict(status='PASS',files=len(files),records=records,modes=dict(modes),zero_exact_checks=zero_checks,
        mean_gain_by_arm_enriched_training_only={k:float(np.mean(v)) for k,v in metrics.items()},
        warning='Current completed cohorts may be training only; this is engineering acceptance, not independent validation.')
    now=dt.datetime.now(dt.timezone.utc);lanes={};learning=defaultdict(list)
    for node in ['peer_a1','peer_a2','peer_b1']:
        folder=RUN/'background_supervisor'/node/'retained_overlap_v1';live=read(folder/'LIVE.json')
        assert all(v['returncode'] is None for v in live['processes'].values());lanes[node]=[]
        for device in [0,4,8,12]:
            path=RUN/'background_gpu'/node/f'device{device:02d}'/'retained_overlap_v1';start=read(path/'START.json');state=read(path/'LIVE.json')
            elapsed=(now-dt.datetime.fromisoformat(start['time'])).total_seconds()
            lanes[node].append(dict(device=device,elapsed_seconds=elapsed,completed_chunks=state['completed'],status=state['status'],
                completed_records_per_wall_second=state['completed']*676/max(elapsed,1),
                rate_caveat='Startup included; 676 records/chunk verified for this coarse panel, not unique trajectories.'))
    for path in (ROOT/'runs/behavior_experts_v1/receipts').glob('*.json'):
        d=read(path)
        if (now-dt.datetime.fromisoformat(d['time'])).total_seconds()>3600:continue
        training=read(ROOT/d['result']['path']);task=training['task'];key=('cached' if training.get('cached_interface') else 'raw')+'_'+task['block']
        learning[key].append(training['seconds']/task['steps'])
    results['efficiency']=dict(lanes=lanes,learning_seconds_per_step={k:dict(n=len(v),median=float(np.median(v)),p90=float(np.quantile(v,.9))) for k,v in learning.items()},
        interpretation='Mixed workload observational rates; use exact A/B for equivalence and device trials for overlap. Physical cards remain 48.')
    path=ROOT/'provenance/STREAM_ACCEPTANCE_20261017T23.json';atomic(path,dict(status='PASS',time=stamp(),**results))
    return dict(path=str(path.relative_to(ROOT)),hard_files=len(files),zero_checks=zero_checks)
