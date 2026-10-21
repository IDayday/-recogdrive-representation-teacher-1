"""Foreground minute monitor: prepare-index boundary, task completion and resource limits."""
from common import *
import argparse
import numpy as np
from subspace_scan_prepare import OUT

def main(args):
    from cloud_api import request
    from subspace_scan_queue import write
    setup('subspace_scan/monitor');cfg=read(ROOT/args.execution);base=ROOT/'runs'/cfg['run'];began=time.monotonic();checked=False
    while True:
        for node in [0,1]:
            bad=base/f'node{node}/FAILED.json'
            assert not bad.exists(),str(bad)
        assert not list((base/'failures').glob('*.json'))
        prepped=all((OUT/f'cache/PREP_NODE{i}_COMPLETE.json').exists() for i in [0,1])
        receipts={p.stem for p in (base/'receipts').glob('*.json')};tasks=read(base/'tasks.json');wanted=[t for t in tasks if t['phase']==args.phase]
        counts={phase:dict(done=sum(t['id'] in receipts for t in tasks if t['phase']==phase),total=sum(t['phase']==phase for t in tasks)) for phase in ['cv','confirm']}
        jobs=[];limits=[]
        for submission in cfg['submissions']:
            job_id=read(ROOT/submission)['JobId']
            for attempt in range(6):
                try:j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job_id);break
                except Exception as error:
                    if attempt==5:raise RuntimeError('Cloud query repeatedly failed: '+type(error).__name__) from None
                    time.sleep(min(.25*2**attempt,4))
            assert j['Status']=='Running',(job_id,j['Status']);jobs.append(dict(JobId=job_id,Status=j['Status']))
            start=dt.datetime.fromisoformat(j['GmtCreateTime'].replace('Z','+00:00'));deadline=start+dt.timedelta(minutes=j['JobMaxRunningTimeMinutes'])
            remain=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds();limits.append(dict(job=job_id,deadline_utc=deadline.isoformat(),remaining_seconds=remain,reserved_minutes=j.get('Settings',{}).get('JobReservedMinutes'),extension_verified=False))
        states=[read(p) for p in (base/'workers').glob('rank*.json')];elapsed=time.monotonic()-began
        status=dict(time=stamp(),cache_ready=prepped,counts=counts,workers=len(states),jobs=jobs,resource_limits=limits,phase=args.phase,elapsed_seconds=elapsed)
        write(base/'MONITOR.json',status);print(json.dumps(status),flush=True)
        if any(r['remaining_seconds']<3600 for r in limits):write(base/'LIMIT_NOTICE.json',status);return
        if elapsed>300 and receipts and not checked:
            selected=sorted(receipts)[-8:]
            for key in selected:
                proof=read(base/'receipts'/(key+'.json'));path=base/'results'/(key+'.json');assert sha(path)==proof['result_sha256']
                doc=read(path);assert doc['status']=='COMPLETE'
                if doc['task']['phase']=='cv':assert not doc['heldout_validation_evaluated'] and len(doc['search'])==1346
            write(base/'SEMANTIC_5MIN.json',dict(status='PASS',time=stamp(),tasks=selected));checked=True
        if wanted and all(t['id'] in receipts for t in wanted) and len(states)==2*cfg['workers_per_node'] and all(s['status']=='QUEUE_WAIT' for s in states):
            assert not read(base/'queue.json')['closed']
            write(base/(args.phase.upper()+'_DRAINED_RESOURCES_HELD.json'),dict(status='PASS',time=stamp(),counts=counts,jobs=jobs,resource_limits=limits))
            print(json.dumps(dict(status='PHASE_DRAINED_RESOURCES_HELD',phase=args.phase)),flush=True);return
        time.sleep(60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',required=True);p.add_argument('--phase',choices=['cv','confirm'],default='cv');main(p.parse_args())
