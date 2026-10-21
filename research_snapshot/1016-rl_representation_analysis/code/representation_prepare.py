"""New train-only GT reference scoring and session-disjoint analysis manifests."""
from common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
import multiprocessing as mp
import pickle
import subprocess


def score_init():
    setup(f'reference_scoring/{os.getpid()}')
    compatibility()


def score_physical(task):
    import lzma
    import numpy as np
    import dataclasses
    from navsim.common.dataclasses import Trajectory
    from navsim.evaluate.pdm_score import pdm_score,get_trajectory_as_array
    from nuplan.planning.simulation.trajectory.trajectory_sampling import TrajectorySampling
    from navsim.planning.simulation.planner.pdm_planner.simulation.pdm_simulator import PDMSimulator
    from navsim.planning.simulation.planner.pdm_planner.scoring.pdm_scorer import PDMScorer,PDMScorerConfig
    data=retry(lambda:Path(task['metric_cache']).read_bytes())
    assert hashlib.sha256(data).hexdigest()==task['metric_sha256']
    cache=pickle.loads(lzma.decompress(data))
    poses=np.asarray(task['trajectory'],dtype=np.float64)
    assert poses.shape==(8,3) and np.isfinite(poses).all()
    sampling=TrajectorySampling(**task['scoring']['proposal_sampling'])
    result=pdm_score(cache,Trajectory(poses,TrajectorySampling(num_poses=8,interval_length=.5)),sampling,
            PDMSimulator(sampling),PDMScorer(sampling,PDMScorerConfig(**task['scoring']['scorer'])))
    values={k:float(v) for k,v in dataclasses.asdict(result).items()}
    assert all(np.isfinite(v) and 0<=v<=1+1e-8 for v in values.values())
    reference=get_trajectory_as_array(cache.trajectory,sampling,cache.ego_state.time_point)
    return dict(token=task['token'],source=task.get('source','unknown'),score=values,
                metric_sha256=task['metric_sha256'],reference_sha256=hashlib.sha256(reference.tobytes()).hexdigest())


def baseline_records(tokens):
    execution=read(ROOT/'configs/execution.json')
    population=list(csv.DictReader((ROOT/'manifests/navtrain.csv').open()))
    groups={}
    for index,row in enumerate(population):
        if row['token'] in tokens:
            rank=index%32;offset=((index//32)//32)*32
            path=ROOT/'runs'/execution['run_id']/'formal'/f'rank{rank:03d}'/'chunks'/f'{offset:06d}.json'
            groups.setdefault(path,set()).add(row['token'])
    records={}
    for path,wanted in groups.items():
        for r in read(path)['records']:
            if r['token'] in wanted:
                records[r['token']]=dict(r,baseline_chunk=str(path))
    assert set(records)==set(tokens)
    return records


def session(log_name):
    return log_name.rsplit('_',2)[0]


def primary_mode(values):
    if values['no_at_fault_collisions']<1:return 'collision'
    if values['drivable_area_compliance']<1:return 'offroad'
    if values['time_to_collision_within_bound']<1:return 'ttc'
    if values['comfort']<1:return 'progress_comfort'
    return 'progress_only'


def prepare(args):
    import torch
    config=read(ROOT/'configs/baseline.json')
    source=ROOT/'runs'/read(ROOT/'configs/execution.json')['run_id']/'delivery/failure_pool.csv'
    rows=list(csv.DictReader(source.open()))
    assert len(rows)==2288 and len({r['token'] for r in rows})==2288
    if args.limit:rows=sorted(rows,key=lambda r:digest(r['token']))[:args.limit]
    records=baseline_records({r['token'] for r in rows})
    output=ROOT/'runs'/args.run;output.mkdir(parents=True,exist_ok=True)
    assert not (output/'references.json').exists()
    sessions=sorted({session(r['log_name']) for r in csv.DictReader((ROOT/'manifests/navtrain.csv').open())},
                    key=lambda s:digest({'session':s,'split_seed':20261016}))
    validation=set(sessions[:max(1,round(len(sessions)*.2))])
    references=[];tasks=[]
    for row in rows:
        r=records[row['token']]
        data=retry(lambda:(Path(row['feature_dir'])/'trajectory_target.gz').read_bytes())
        assert hashlib.sha256(data).hexdigest()==r['target_sha256']
        gt=pickle.loads(gzip.decompress(data))['trajectory']
        assert tuple(gt.shape)==(8,3) and torch.isfinite(gt).all()
        group=session(row['log_name'])
        references.append(dict(r,session=group,subset='validation' if group in validation else 'exploration',
                               gt_trajectory=gt.double().numpy().tolist(),gt_original_dtype=str(gt.dtype),
                               failure_modes=[key for key in ['no_at_fault_collisions','drivable_area_compliance',
                                 'time_to_collision_within_bound','comfort'] if r['score'][key]<1],
                               primary_mode=primary_mode(r['score'])))
        tasks.append(dict(token=r['token'],source='GT',trajectory=references[-1]['gt_trajectory'],
                          metric_cache=r['metric_cache'],metric_sha256=r['metric_sha256'],scoring=config['scoring']))
    atomic(output/'scoring_request.json',tasks)
    atomic(output/'STATUS.json',dict(status='SCORING_GT',time=stamp(),total=len(tasks),workers=args.workers))
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn'),initializer=score_init) as pool:
        for index,result in enumerate(pool.map(score_physical,tasks),1):
            results.append(result)
            if index%64==0:
                atomic(output/'STATUS.json',dict(status='SCORING_GT',time=stamp(),completed=index,total=len(tasks)))
                print(json.dumps(dict(completed=index,total=len(tasks))),flush=True)
    for r,scored in zip(references,results):
        assert r['token']==scored['token'] and r['reference_sha256']==scored['reference_sha256']
        r['gt_score']=scored['score']
        r['original_gt_high_quality']=scored['score']['score']>.9
        r['eligible']=True  # Original GT scores are diagnostic; label only after complete denoising and rescoring.
        r['exclusion_reason']=None
    # A standalone original-source process verifies both GT and baseline trajectories.
    probe=tasks[:4]+[dict(tasks[i],source='baseline',trajectory=references[i]['trajectory']) for i in range(min(4,len(tasks)))]
    atomic(output/'independent_request.json',probe)
    subprocess.run([sys.executable,'-B',str(Path(__file__)),'score','--request',str(output/'independent_request.json'),
        '--response',str(output/'independent_original.json'),'--original-source',config['shared_reference_source']],check=True,cwd=ROOT,timeout=600)
    actual=read(output/'independent_original.json')['results']
    by={r['token']:r for r in references}
    for result in actual:
        wanted=by[result['token']]['gt_score' if result['source']=='GT' else 'score']
        assert result['score']==wanted,(result['token'],result['source'])
    atomic(output/'references.json',references)
    from collections import Counter
    eligible=[r for r in references if r['eligible']]
    stats=dict(status='COMPLETE',time=stamp(),run=args.run,total=len(references),eligible=len(eligible),
               excluded=len(references)-len(eligible),subsets=dict(Counter(r['subset'] for r in eligible)),
               modes=dict(Counter(r['primary_mode'] for r in eligible)),
               sessions_total=len(sessions),failure_sessions=len({r['session'] for r in references}),
               original_gt_quality_counts=dict(Counter(quality(r['gt_score']['score']) for r in references)),
               exploration_validation_sessions_disjoint=True,validation_fraction=.2,split_seed=20261016,
               session_definition='log_name.rsplit("_",2)[0]; all segments from the same collection session stay together',
               gt_dtype='preserve original float64 physical coordinates; model outputs retain their exact float32 values',
               baseline_pdms_threshold_lt=.7,gt_original_score_used_for_admission=False,
               final_analysis_thresholds=dict(failure_lt=.7,high_quality_gt=.9),independent_original_source_equal=True,
               references_sha256=sha(output/'references.json'),baseline_identity=config['identity'],test_cache_access=False)
    atomic(output/'COMPLETE.json',stats);atomic(output/'STATUS.json',stats)
    print(json.dumps(stats),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','score'])
    parser.add_argument('--run');parser.add_argument('--workers',type=int,default=4);parser.add_argument('--limit',type=int)
    parser.add_argument('--request',type=Path);parser.add_argument('--response',type=Path);parser.add_argument('--original-source',type=Path)
    args=parser.parse_args();setup('representation_prepare');compatibility()
    if args.command=='prepare':prepare(args)
    else:
        if args.original_source:sys.path.insert(0,str(args.original_source))
        results=[score_physical(task) for task in read(args.request)]
        import importlib
        origin=importlib.import_module('navsim.evaluate.pdm_score').__file__
        if args.original_source:assert Path(origin).resolve().is_relative_to(args.original_source.resolve())
        atomic(args.response,dict(status='PASS',python=sys.executable,source=origin,results=results))


if __name__=='__main__':main()
