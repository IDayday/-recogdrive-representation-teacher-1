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
        for trial in (ROOT/'runs/extra_engineering_v1').glob('*'):
            if (trial/'FAILED.json').exists() and not (trial/'FAILURE_REVIEW.json').exists():
                print(json.dumps(dict(event='EXTRA_LANE_FAILED_REQUIRES_REVIEW',path=str(trial),detail=read(trial/'FAILED.json'),**summary)),flush=True);return
            if (trial/'PASS.json').exists() and not (trial/'AGENT_ACCEPTANCE.json').exists():
                print(json.dumps(dict(event='EXTRA_LANE_ENGINEERING_READY',path=str(trial),**summary)),flush=True);return
            if (trial/'AGENT_ACCEPTANCE.json').exists() and not (trial/'THROUGHPUT_REVIEW.json').exists():
                passed=dt.datetime.fromisoformat(read(trial/'PASS.json')['time'])
                if (dt.datetime.now(dt.timezone.utc)-passed).total_seconds()>=600:
                    print(json.dumps(dict(event='EXTRA_LANE_TRIAL_WINDOW_COMPLETE',path=str(trial),**summary)),flush=True);return
        registry=read(ROOT/'resources/REGISTRY.json');cloud=read(BATCH2/'resources/CLOUD_LATEST.json')
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
