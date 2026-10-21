"""Mechanical 60s watcher for compact stages, nodes and registered async work."""
from r3_common import *
import argparse


def event(name,**values):
    print(json.dumps(dict(event=name,time=stamp(),**values),ensure_ascii=False),flush=True)


def main(a):
    began=time.monotonic();queue_path=ROOT/'runs/ELASTIC_STAGE_QUEUE.json'
    while True:
        queue=read(queue_path);progress=[]
        lease_failure=next((ROOT/'runs/elastic_stage_service_v1_leases/failures').glob('*.json'),None)
        if lease_failure:event('ELASTIC_LEASE_FAILED',path=str(lease_failure));return
        for setting in sorted(queue['stages'],key=lambda v:(v['priority'],v['id'])):
            stage=ROOT/setting['stage']
            if (stage/'AGENT_ACCEPTANCE.json').exists():continue
            for folder in ['failures','audit_v1/failures']:
                failed=next((stage/folder).glob('*.json'),None)
                if failed:event('STAGE_FAILED_REQUIRES_REVIEW',stage=setting['id'],path=str(failed));return
            if (stage/'AUDIT_COMPLETE.json').exists():
                event('STAGE_COMPUTE_AND_CPU_AUDIT_COMPLETE',stage=setting['id'],path=str(stage));return
            if not (stage/'claims').exists():continue
            spec=read(stage/'SPECIFICATION.json');total=(spec['case_count']+spec['chunk_size']-1)//spec['chunk_size']
            count=len(list((stage/'receipts').glob('*.json')))
            progress.append(dict(stage=setting['id'],completed_chunks=count,total_chunks=total))
            review=ROOT/'provenance/formed_phase_reviews_v1'/(setting['id']+'.json')
            if not review.exists() and count>0 and time.monotonic()-began>=a.check_after:
                event('FORMED_STAGE_EARLY_PHASE_REVIEW',stage=setting['id'],progress=progress);return
        for watch in read(ROOT/'resources/ASYNC_WATCHES.json')['watches']:
            if (ROOT/watch['acknowledgement']).exists():continue
            for key in ['failure','success']:
                if watch.get(key) and (ROOT/watch[key]).exists():
                    event('ASYNC_'+key.upper()+'_REQUIRES_REVIEW',watch=watch['id'],path=watch[key]);return
        cloud=read(BATCH2/'resources/CLOUD_LATEST.json');registry=read(ROOT/'resources/REGISTRY.json')
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds()
        if age>600:event('CLOUD_STATUS_SOURCE_STALE',age_seconds=age);return
        known={v['job'] for v in registry['nodes']}
        changed=[v for v in cloud['nodes'] if v['job'] in known and v['status']!='Running']
        if changed:event('KNOWN_NODE_CHANGED_STATE',nodes=changed);return
        new=[v for v in cloud['nodes'] if v['status']=='Running' and v['job'] in registry.get('pending_jobs',[])]
        if new:event('NEW_RUNNING_NODE_REQUIRES_PREFLIGHT',nodes=new);return
        near=[v for v in cloud['nodes'] if v['job'] in known and v['status']=='Running' and v.get('remaining_seconds',999999)<7200]
        if near:event('NODE_DEADLINE_WITHIN_TWO_HOURS',nodes=near);return
        for path in (ROOT/'runs/elastic_stage_workers').glob('*.json'):
            live=read(path)
            if live['status']=='COMPUTING' and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()>1200:
                event('LONG_UNCHANGED_WORK_ITEM_REQUIRES_REVIEW',worker=live);return
        if all((ROOT/v['stage']/'AGENT_ACCEPTANCE.json').exists() for v in queue['stages']):
            event('ALL_CURRENT_REGISTERED_STAGES_ACCEPTED',scope='Current registry only; wide and GT phases may remain');return
        atomic(ROOT/'runs/ELASTIC_MONITOR.json',dict(status='RUNNING',time=stamp(),interval_seconds=a.interval,progress=progress))
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--interval',type=int,default=60);p.add_argument('--check-after',type=int,default=420);main(p.parse_args())
