"""Mechanical workload wait: wake on review boundaries, errors or new capacity."""
from r3_common import *
import argparse


def main(a):
    stage=ROOT/'runs'/a.stage;began=time.monotonic();last_report=-1;first=None
    producer=read(stage/'producer.json');total=producer['tasks'];cases=producer['cases']
    while True:
        failures=list((stage/'failures').glob('*.json'))+list((stage/'audit_v1/failures').glob('*.json'))+list((ROOT/'runs'/(a.stage+'_leases')/'failures').glob('*.json'))
        if failures:
            print(json.dumps(dict(event='TASK_FAILED_REQUIRES_REVIEW',time=stamp(),path=str(failures[0]),detail=read(failures[0])),ensure_ascii=False),flush=True);return
        done=list((stage/'receipts').glob('*.json'));count=len(done)
        if first is None:first=count
        summary=dict(time=stamp(),stage=a.stage,completed_tasks=count,total_tasks=total,completed_cases_upper=min(count*producer['chunk_size'],cases),total_cases=cases,elapsed_wait_seconds=time.monotonic()-began)
        if count==total:
            print(json.dumps(dict(event='COMPLETE_REQUIRES_ACCEPTANCE',**summary)),flush=True);return
        for trial in (ROOT/'runs/concurrency_trials_v1').glob('*'):
            if (trial/'REVIEW.json').exists():continue
            for marker in ['FAILED.json','COMPLETE.json']:
                if (trial/marker).exists():
                    print(json.dumps(dict(event='BOUNDED_CONCURRENCY_TRIAL_REQUIRES_REVIEW',path=str(trial),detail=read(trial/marker),**summary)),flush=True);return
        watches_path=ROOT/'resources/ASYNC_WATCHES.json'
        if watches_path.exists():
            for watch in read(watches_path)['watches']:
                if (ROOT/watch['acknowledgement']).exists():continue
                failed=ROOT/watch['failure'] if watch.get('failure') else None
                complete=ROOT/watch['success']
                if failed is not None and failed.exists():
                    print(json.dumps(dict(event='ASYNC_TASK_FAILED_REQUIRES_REVIEW',watch=watch['id'],path=str(failed),detail=read(failed),**summary)),flush=True);return
                if complete.exists():
                    print(json.dumps(dict(event='ASYNC_TASK_COMPLETED_REQUIRES_REVIEW',watch=watch['id'],path=str(complete),**summary)),flush=True);return
        grouped=set()
        for group_path in sorted((ROOT/'resources').glob('EXTRA_GROUP_V*.json')):
            group=read(group_path);members={v['worker'] for v in group['workers']};grouped.update(members);ready_workers=[];group_name=group_path.stem
            for worker in sorted(members):
                folder=ROOT/'runs/extra_engineering_v1'/worker
                if (folder/'FAILED.json').exists() and not (folder/'FAILURE_REVIEW.json').exists():
                    print(json.dumps(dict(event='EXTRA_GROUP_LANE_FAILED',group=group_name,worker=worker,path=str(folder),detail=read(folder/'FAILED.json'),**summary)),flush=True);return
                if (folder/'PASS.json').exists():ready_workers.append(worker)
            accepted=ROOT/'provenance'/(group_name+'_ACCEPTANCE.json')
            if len(ready_workers)==len(members) and not accepted.exists():
                print(json.dumps(dict(event='EXTRA_GROUP_ALL_READY_FOR_ACCEPTANCE',group=group_name,workers=ready_workers,**summary)),flush=True);return
            if accepted.exists() and not (ROOT/'provenance'/(group_name+'_PHASE_ACCEPTANCE.json')).exists():
                admitted=dt.datetime.fromisoformat(read(accepted)['time'])
                if (dt.datetime.now(dt.timezone.utc)-admitted).total_seconds()>=360:
                    print(json.dumps(dict(event='EXTRA_GROUP_EARLY_PHASE_REVIEW',group=group_name,**summary)),flush=True);return
        for trial in (ROOT/'runs/extra_engineering_v1').glob('*'):
            if trial.name in grouped:continue
            if (trial/'FAILED.json').exists() and not (trial/'FAILURE_REVIEW.json').exists():
                print(json.dumps(dict(event='EXTRA_LANE_FAILED_REQUIRES_REVIEW',path=str(trial),detail=read(trial/'FAILED.json'),**summary)),flush=True);return
            if (trial/'PASS.json').exists() and not (trial/'AGENT_ACCEPTANCE.json').exists():
                print(json.dumps(dict(event='EXTRA_LANE_ENGINEERING_READY',path=str(trial),**summary)),flush=True);return
            if (trial/'AGENT_ACCEPTANCE.json').exists() and not (trial/'THROUGHPUT_REVIEW.json').exists():
                passed=dt.datetime.fromisoformat(read(trial/'PASS.json')['time'])
                if (dt.datetime.now(dt.timezone.utc)-passed).total_seconds()>=600:
                    print(json.dumps(dict(event='EXTRA_LANE_TRIAL_WINDOW_COMPLETE',path=str(trial),**summary)),flush=True);return
        registry=read(ROOT/'resources/REGISTRY.json');cloud=read(BATCH2/'resources/CLOUD_LATEST.json')
        cloud_age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds()
        if cloud_age>600:
            print(json.dumps(dict(event='CLOUD_STATUS_SOURCE_STALE',cloud_age_seconds=cloud_age,**summary)),flush=True);return
        known_jobs={v['job'] for v in registry['nodes']}
        unexpected=[v for v in cloud['nodes'] if v['job'] in known_jobs and v['status']!='Running']
        if unexpected:
            print(json.dumps(dict(event='KNOWN_NODE_CHANGED_STATE',nodes=unexpected,**summary)),flush=True);return
        for heartbeat in (stage/'workers').glob('*.json'):
            h=read(heartbeat)
            if h['status']=='COMPUTING' and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(h['time'])).total_seconds()>1200:
                print(json.dumps(dict(event='LONG_UNCHANGED_WORK_ITEM_REQUIRES_REVIEW',worker=h,**summary)),flush=True);return
        new=[v for v in cloud['nodes'] if v['status']=='Running' and v['job'] in registry.get('pending_jobs',[])]
        if new:
            print(json.dumps(dict(event='NEW_RUNNING_NODE_REQUIRES_PREFLIGHT',nodes=new,**summary)),flush=True);return
        current={n['job'] for n in registry['nodes']};near=[v for v in cloud['nodes'] if v['job'] in current and v['status']=='Running' and v.get('remaining_seconds',999999)<7200]
        if near:
            print(json.dumps(dict(event='NODE_DEADLINE_WITHIN_TWO_HOURS',nodes=near,**summary)),flush=True);return
        if a.check_after and time.monotonic()-began>=a.check_after:
            print(json.dumps(dict(event='EARLY_PHASE_REVIEW',**summary)),flush=True);return
        if a.timeout and time.monotonic()-began>=a.timeout:
            print(json.dumps(dict(event='SCHEDULED_REVIEW',**summary)),flush=True);return
        hour=int((time.monotonic()-began)//3600)
        if True:
            atomic(stage/'MONITOR.json',dict(event='RUNNING',**summary));last_report=hour
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--interval',type=int,default=60);p.add_argument('--check-after',type=int,default=0);p.add_argument('--timeout',type=int,default=0);main(p.parse_args())
