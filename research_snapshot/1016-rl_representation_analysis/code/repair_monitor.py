"""One-minute foreground terminal monitor, yielding to the agent at required stage boundaries."""
from common import *
import argparse

def main(args):
    from cloud_api import request
    execution=read(ROOT/args.execution);base=ROOT/'runs'/execution['run'];began=time.monotonic();last_checked=set()
    while True:
        tasks=read(base/'tasks.json');receipts={p.stem for p in (base/'receipts').glob('*.json')} if (base/'receipts').exists() else set()
        counts={s:dict(total=sum(t['stage']==s for t in tasks),done=sum(t['id'] in receipts for t in tasks if t['stage']==s)) for s in sorted({t['stage'] for t in tasks})}
        nodes=[];jobs=[];limits=[]
        for i in range(2):
            p=base/f'node{i}/STATUS.json'
            if p.exists():nodes.append(read(p))
            job=read(ROOT/execution['submissions'][i])['JobId']
            try:
                j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
                jobs.append({k:j[k] for k in ['JobId','Status','ReasonCode','ReasonMessage'] if k in j})
                now=dt.datetime.now(dt.timezone.utc);minutes=j.get('JobMaxRunningTimeMinutes',720)
                starts={k:dt.datetime.fromisoformat(j[k].replace('Z','+00:00')) for k in ['GmtCreateTime','GmtRunningTime'] if j.get(k)}
                deadlines={k:(v+dt.timedelta(minutes=minutes)).isoformat() for k,v in starts.items()}
                remaining=min((v+dt.timedelta(minutes=minutes)-now).total_seconds() for v in starts.values()) if minutes else None
                limits.append(dict(job=job,max_running_minutes=minutes,reserved_minutes=j.get('Settings',{}).get('JobReservedMinutes'),
                    deadlines_utc=deadlines,conservative_remaining_seconds=remaining,extension_verified=False))
            except Exception as e:jobs.append(dict(JobId=job,Status='QUERY_ERROR',error=str(e)))
        status=dict(time=stamp(),jobs=jobs,nodes=nodes,stages=counts,queue=read(base/'queue.json'),seconds=time.monotonic()-began,resource_limits=limits)
        atomic(base/'MONITOR.json',status);print(json.dumps(status),flush=True)
        failures=list((base/'failures').glob('*.json')) if (base/'failures').exists() else []
        if failures or any((base/f'node{i}/FAILED.json').exists() for i in range(2)) or any(j['Status'] in ['Failed','Stopped','Deleted'] for j in jobs):
            raise RuntimeError(f'Repair job failed: {failures}; inspect original exceptions')
        if any(v['conservative_remaining_seconds'] is not None and v['conservative_remaining_seconds']<3600 for v in limits):
            atomic(base/'LIMIT_NOTICE.json',dict(status='ATTENTION_REQUIRED',time=stamp(),limits=limits,resources_not_stopped=True))
            print(json.dumps(dict(status='LIMIT_NOTICE',limits=limits)),flush=True);return
        # Every ~5min inspect actual fresh cases, hashes, bounds, identity scoring, and source/seed semantics.
        if time.monotonic()-began>=300:
            new=sorted(receipts-last_checked)
            if new:
                sample=new[-min(8,len(new)):];tested=0
                for key in sample:
                    rec=read(base/'receipts'/f'{key}.json');path=base/'results'/f'{key}.json'
                    assert sha(path)==rec['result_sha256'];result=read(path);by={}
                    for r in result['records']:
                        assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(r['score']['score'])
                        assert r['score']['score']==r['score']['score']
                        by.setdefault(r['token'],[]).append(r)
                    for token,rr in by.items():assert sum(r['arm']=='baseline' for r in rr)==1
                    tested+=len(result['records'])
                atomic(base/'stage_checks'/f'{int(time.monotonic()-began):06d}.json',dict(status='PASS',time=stamp(),sampled_tasks=sample,records=tested))
                last_checked=receipts
        if args.until:
            needed=args.until.split(',')
            if all(s in counts and counts[s]['done']==counts[s]['total'] for s in needed):
                print(json.dumps(dict(status='STAGE_READY',stages=needed,time=stamp())),flush=True);return
        elif args.retain and all(v['done']==v['total'] for v in counts.values()):
            states=[read(base/'workers'/f'rank{r:03d}.json') for r in range(32)]
            if all(v['status'] in ['QUEUE_WAIT','COMPLETE'] for v in states):
                assert not status['queue']['closed'] and all(j['Status']=='Running' for j in jobs)
                atomic(base/'COMPUTE_DRAINED_RESOURCES_HELD.json',dict(status='PASS',time=stamp(),jobs=jobs,stages=counts,limits=limits))
                print(json.dumps(dict(status='COMPUTE_DRAINED_RESOURCES_HELD',time=stamp())),flush=True);return
        elif not args.retain and all(j['Status']=='Succeeded' for j in jobs):
            assert all(v['done']==v['total'] for v in counts.values()) and status['queue']['closed']
            atomic(base/'MONITOR_COMPLETE.json',dict(status='PASS',time=stamp(),jobs=jobs,stages=counts));return
        time.sleep(60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--until');p.add_argument('--execution',default='configs/repair_execution_v1.json');p.add_argument('--retain',action='store_true');args=p.parse_args();setup('repair/monitor');main(args)
