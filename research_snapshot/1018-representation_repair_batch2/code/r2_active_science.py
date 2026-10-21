"""Mechanical readable view of actual science under nested admission carriers."""
from r2_common import *
from collections import Counter


def leaf(carrier):
    stage=carrier['canonical_stage'];task=carrier['canonical_task'];handler=carrier['scientific_handler']
    for _ in range(5):
        if 'canonical_stage' not in task:return stage,task,handler
        stage=task['canonical_stage'];handler=task['scientific_handler'];task=task['canonical_task']
    raise ValueError('Unexpected admission nesting')


def main():
    tables={};versions={}
    while True:
        observed=[];now=dt.datetime.now(dt.timezone.utc)
        for path in (RUN/'dispatch_workers').glob('*.json'):
            state=read(path)
            if state.get('status')!='COMPUTING':continue
            worker=path.stem;stage=state['stage'];task_id=state['task'];name=stage;task=None
            if stage.startswith('runs/fair_scientific_admission_v1/g'):
                source=ROOT/stage/'tasks.json';version=source.stat().st_mtime_ns
                if versions.get(stage)!=version:tables[stage]={t['id']:t for t in read(source)};versions[stage]=version
                carrier=tables[stage][task_id];name,task,handler=leaf(carrier)
            detail={k:task[k] for k in ['system','K','expert','block','heldout_fold','fit_seed','kind','tier','role','steps'] if task is not None and k in task}
            observed.append(dict(worker=worker,science_stage=name,canonical_task=task['id'] if task is not None else task_id,
                source_dispatch_stage=stage,task_started=state['time'],elapsed_seconds=(now-dt.datetime.fromisoformat(state['time'])).total_seconds(),configuration=detail))
        atomic(RUN/'active_science/LIVE.json',dict(time=stamp(),primary_workers_observed=len(observed),actual_science_counts=dict(Counter(o['science_stage'] for o in observed)),workers=observed,
            supplementary_gpu_lanes='Separate background_gpu records; do not count them as extra physical cards.',
            supervision='Read-only mechanical task view; no scheduling decisions, no process stops.'))
        time.sleep(60)


if __name__=='__main__':main()
