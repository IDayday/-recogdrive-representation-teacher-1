"""Actual scenario/optimizer-step accounting for one bounded overlap trial.

Different scientific stage workloads are kept separate. Mixed record counts are
not interpreted as a speedup, and straddling task boundaries are reported.
"""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict


def run(task):
    import numpy as np
    folder=ROOT/task['trial'];start=read(folder/'START.json');end=read(folder/'COMPLETE.json');a=dt.datetime.fromisoformat(start['time']);b=dt.datetime.fromisoformat(end['time']);duration=(b-a).total_seconds();lower=a-dt.timedelta(seconds=duration)
    primary_pid=read(RUN/'nodes'/start['node']/'LIVE.json')['children']['gpu_1_'+str(start['device'])]['pid'];primary=start['worker'].rsplit('_',1)[0]+'_'+str(primary_pid)
    directories=[]
    for config in read(ROOT/'config/GPU_STAGES.json')['stages']:
        base=ROOT/config['path'];worker=base/'workers'/(primary+'.json')
        if worker.exists() and worker.stat().st_mtime>=lower.timestamp():directories.append(base)
    paths=[]
    for base in dict.fromkeys(directories):
        for path in (base/'receipts').glob('*.json'):
            if lower.timestamp()-60<=path.stat().st_mtime<=b.timestamp()+60:paths.append(path)
    def inspect(path):
        r=read(path)
        if r['worker']!=primary:return None
        t=dt.datetime.fromisoformat(r['time']);interval='before' if lower<=t<a else 'during' if a<=t<=b else None
        if interval is None:return None
        scientific=r['task'];stage=str(path.parent.parent.relative_to(ROOT))
        while 'canonical_task' in scientific:stage=scientific['canonical_stage'];scientific=scientific['canonical_task']
        result=r['result']
        while isinstance(result,dict) and 'status' in result:
            if result['status'] in ['ALREADY_COMPLETE','ALREADY_CLAIMED']:return None
            if 'result' not in result:break
            result=result['result']
        began=t-dt.timedelta(seconds=r['seconds']);contained=began>=(lower if interval=='before' else a)
        return dict(interval=interval,stage=stage,id=scientific['id'],scenes=max(0,scientific.get('end',0)-scientific.get('start',0)),steps=scientific.get('steps',0),block=scientific.get('block'),seconds=r['seconds'],fully_contained=contained,path=str(path.relative_to(ROOT)),records=result.get('records',0) if isinstance(result,dict) else 0)
    with ThreadPoolExecutor(max_workers=8) as pool:records=[r for r in pool.map(inspect,paths) if r is not None]
    unique={}
    for r in records:unique[(r['stage'],r['id'])]=r
    records=list(unique.values());groups=defaultdict(list)
    for r in records:groups[(r['interval'],r['stage'],r['block'])].append(r)
    summaries=[]
    for (interval,stage,block),items in sorted(groups.items(),key=lambda p:str(p[0])):
        normalized=[v['seconds']/v['steps'] for v in items if v['steps']];summaries.append(dict(interval=interval,stage=stage,block=block,tasks=len(items),scenario_evaluations=sum(v['scenes'] for v in items),optimizer_steps=sum(v['steps'] for v in items),fully_contained_tasks=sum(v['fully_contained'] for v in items),median_task_seconds=float(np.median([v['seconds'] for v in items])),median_seconds_per_optimizer_step=float(np.median(normalized)) if normalized else None))
    extra=defaultdict(lambda:dict(tasks=0,scenario_evaluations=0,records=0,seconds=[]))
    for r in end['receipts']:
        stage=str(Path(r['result']['path']).parent.parent);x=extra[stage];x['tasks']+=1;x['scenario_evaluations']+=r['task']['end']-r['task']['start'];x['records']+=r['result']['records'];x['seconds'].append(r['seconds'])
    for v in extra.values():v['median_task_seconds']=float(np.median(v.pop('seconds')))
    destination=ROOT/'analysis/overlap_trials'/task['id'];atomic(destination.with_suffix('.json'),dict(status='DESCRIPTIVE_OVERLAP_TRIAL_ACCOUNTING',time=stamp(),task=task,primary_worker=primary,before=[lower.isoformat(),a.isoformat()],during=[a.isoformat(),b.isoformat()],duration_seconds=duration,primary=summaries,supplementary=dict(extra),primary_records=records,
        limitations=['Sequential windows have different task mixtures and evolving caches; not a randomized matched-work benchmark.','Completion accounting includes tasks started earlier; fully-contained counts are also reported.','Extra scenarios do not by themselves prove no primary slowdown. Do not turn mixed output-record counts into a speedup.'],scientific_program_seed_and_score_unchanged=True,physical_cards_added=0));return dict(path=str(destination.with_suffix('.json').relative_to(ROOT)),primary_receipts=len(records))
