"""Quiet mechanical wait for one checkpoint; preserve compute and resources."""
from r3_common import *
import argparse


def main(a):
    while True:
        failures=[p for folder in a.failure_dir for p in (ROOT/folder).glob('*.json')]
        if failures:
            print(json.dumps(dict(event='CHECKPOINT_FAILED_REQUIRES_REVIEW',time=stamp(),path=str(failures[0]))),flush=True);return
        if (ROOT/a.success).exists():
            print(json.dumps(dict(event='CHECKPOINT_READY_REQUIRES_REVIEW',time=stamp(),path=a.success)),flush=True);return
        cloud=read(BATCH2/'resources/CLOUD_LATEST.json');registry=read(ROOT/'resources/REGISTRY.json')
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds()
        if age>600:
            print(json.dumps(dict(event='CLOUD_STATUS_SOURCE_STALE',time=stamp(),age_seconds=age)),flush=True);return
        known={n['job'] for n in registry['nodes']}
        new=[n for n in cloud['nodes'] if n['job'] in registry.get('pending_jobs',[]) and n['status']=='Running']
        changed=[n for n in cloud['nodes'] if n['job'] in known and (n['status']!='Running' or n.get('remaining_seconds',999999)<7200)]
        if new or changed:
            print(json.dumps(dict(event='NODE_EVENT_REQUIRES_REVIEW',time=stamp(),new=new,changed=changed)),flush=True);return
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--success',required=True);p.add_argument('--failure-dir',action='append',default=[])
    p.add_argument('--interval',type=int,default=60);main(p.parse_args())
