"""60s mechanical wait for teacher replay or node scheduling events."""
from d4_common import *
import argparse


def main(a):
    began=time.monotonic();engineering=ROOT/'runs/replay_multidevice_v1';stage=ROOT/'runs/full_context_replay_v1'
    while True:
        failures=[p for f in [engineering/'failures',stage/'failures',stage/'audit/failures',B3/'runs/batch4_teacher_replay_bridge_v1/failures'] for p in f.glob('*.json')]
        event=None;values={}
        if failures:event='REPLAY_FAILED_REQUIRES_REVIEW';values['path']=str(failures[0])
        elif a.mode=='engineering' and (engineering/'ALL_DEVICES_READY.json').exists():event='ALL_REPLAY_DEVICES_READY_REQUIRES_ACCEPTANCE'
        elif a.mode=='replay':
            config=read(ROOT/'configs/REPLAY_SERVICE_V1.json');expected=(config['case_count']+config['chunk_size']-1)//config['chunk_size']
            count=len(list((stage/'receipts').glob('*.json')))
            values.update(completed_chunks=count,total_chunks=expected)
            audited=len(list((stage/'audit/shards').glob('*.json')))
            values['audited_chunks']=audited
            if count==expected and audited==expected:event='FULL_R2_CONTEXT_REPLAY_AND_CPU_AUDIT_COMPLETE_REQUIRES_ACCEPTANCE'
            elif a.check_after and time.monotonic()-began>=a.check_after:event='R2_REPLAY_EARLY_PHASE_REVIEW'
        ddp=ROOT/'runs/ddp_smoke_v1'
        if event is None and ddp.exists() and not (ROOT/'provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V1.json').exists():
            bad=list(ddp.glob('*/rank*_FAILED.json'))
            nodes=read(ROOT/'resources/ALLOCATION_V1.json')['nodes']
            if bad:event='DDP_SMOKE_FAILED_REQUIRES_REVIEW';values['path']=str(bad[0])
            elif all((ddp/n['node']/'ALL_RANKS_PASS.json').exists() for n in nodes):event='DDP_ALL_THREE_NODES_READY_REQUIRES_REVIEW'
        cloud=read(B2/'resources/CLOUD_LATEST.json');registry=read(B3/'resources/REGISTRY.json')
        if event is None:
            age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds()
            known={v['job'] for v in registry['nodes']}
            changed=[n for n in cloud['nodes'] if n['job'] in known and (n['status']!='Running' or n.get('remaining_seconds',999999)<7200)]
            new=[n for n in cloud['nodes'] if n['job'] in registry.get('pending_jobs',[]) and n['status']=='Running']
            if age>600:event='CLOUD_STATUS_SOURCE_STALE';values['age_seconds']=age
            elif new or changed:event='NODE_EVENT_REQUIRES_REVIEW';values.update(new=new,changed=changed)
        if event:
            print(json.dumps(dict(event=event,time=stamp(),**values),ensure_ascii=False),flush=True);return
        atomic(ROOT/'runs/REPLAY_MONITOR.json',dict(status='RUNNING',time=stamp(),mode=a.mode,interval_seconds=a.interval,**values))
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['engineering','replay'],required=True)
    p.add_argument('--interval',type=int,default=60);p.add_argument('--check-after',type=int,default=0);main(p.parse_args())
