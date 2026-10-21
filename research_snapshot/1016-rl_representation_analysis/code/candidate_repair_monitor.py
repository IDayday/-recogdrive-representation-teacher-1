"""Minute polling of task-owned jobs, receipts, failures and lifetime; no automatic recovery."""
from common import *
import argparse
from cloud_api import request
from candidate_repair_fit import OUT

def snapshot(until):
    cfg=read(ROOT/'configs/candidate_repair_execution_v1.json');base=ROOT/'runs'/cfg['run'];jobs=[]
    failures=list((base/'failures').glob('*.json'))+list(base.glob('node*/FAILED.json'))
    if failures:raise RuntimeError('Original failure retained: '+str(failures[0]))
    for p in cfg['submissions']:
        job=read(ROOT/p)['JobId'];j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        created=dt.datetime.fromisoformat(j['GmtCreateTime'].replace('Z','+00:00'));minutes=j['JobMaxRunningTimeMinutes']
        remaining=(created+dt.timedelta(minutes=minutes)-dt.datetime.now(dt.timezone.utc)).total_seconds()
        value={k:j.get(k) for k in ['JobId','Status','ReasonCode','ReasonMessage']};value.update(remaining_seconds=remaining,max_minutes=minutes,reserved_minutes=j.get('Settings',{}).get('JobReservedMinutes'))
        jobs.append(value)
        if j['Status'] in ['Failed','Stopped','Succeeded']:raise RuntimeError('Unexpected terminal job while queue retained: '+str(value))
        if remaining<3600:atomic(OUT/'LIFETIME_NOTICE.json',dict(time=stamp(),job=job,remaining_seconds=remaining))
        if remaining<600:raise RuntimeError('Less than ten minutes lifetime; review pending tasks and resource continuity')
    stages={}
    for p in sorted((base/'stages').glob('*/PROTOCOL.json')):
        protocol=read(p);name=p.parent.name;done=sum(1 for _ in (base/'receipts').glob(name+'_s*.json'))
        stages[name]=dict(done=done,total=protocol['tasks'],complete=done==protocol['tasks'])
    workers=[read(p) for p in (base/'workers').glob('rank[0-9][0-9][0-9].json')]
    from collections import Counter
    value=dict(time=stamp(),until=until,jobs=jobs,stages=stages,worker_states=dict(Counter(w['status'] for w in workers)),
        smoke_nodes=[i for i in range(2) if (base/f'node{i}/SMOKE_PASS.json').exists()])
    atomic(OUT/'MONITOR.json',value)
    print(json.dumps(value,ensure_ascii=False),flush=True)
    return until in stages and stages[until]['complete']

def wait(until):
    while True:
        try:done=snapshot(until)
        except (OSError,TimeoutError) as error:
            print(json.dumps(dict(event='TRANSIENT_MONITOR_READ',time=stamp(),error=repr(error))),flush=True);time.sleep(10);continue
        if done:
            print(json.dumps(dict(event='STAGE_READY',stage=until,time=stamp())),flush=True);return
        time.sleep(60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--until',required=True);args=p.parse_args();wait(args.until)
