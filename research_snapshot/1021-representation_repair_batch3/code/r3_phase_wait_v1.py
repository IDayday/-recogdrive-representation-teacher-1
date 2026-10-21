"""Quiet tool-owned wait for semantic-admission boundaries or errors."""
from r3_common import *
import argparse


def inspect():
    registry=read(ROOT/'resources/REGISTRY.json');ready=[]
    for node in registry['nodes']:
        if (ROOT/'resources/nodes'/node['name']/'THIRD_BATCH_GPU_ACCEPTED.json').exists():continue
        folder=ROOT/'runs/resident_engineering_v1'/node['name'];missing=[]
        for device in node['devices']:
            path=folder/('device%02d'%device)
            if (path/'FAILED.json').exists():return dict(event='ENGINEERING_FAILED',path=str(path/'FAILED.json'),detail=read(path/'FAILED.json'))
            if not (path/'PASS.json').exists():missing.append(device)
        if not missing:ready.append(node['name'])
    if ready:return dict(event='NODE_ENGINEERING_READY_FOR_ACCEPTANCE',nodes=ready)
    queue=ROOT/'runs/QUEUE.json'
    if queue.exists():
        stages=sorted({t['stage'] for t in read(queue)['tasks']})
        for name in stages:
            folder=ROOT/name;failures=list((folder/'failures').glob('*.json'))
            unresolved=[p for p in failures if not (folder/'failure_acknowledgments'/p.name).exists()]
            if unresolved:return dict(event='TASK_FAILED',path=str(unresolved[0]),detail=read(unresolved[0]))
            producer=folder/'producer.json'
            if producer.exists() and not (folder/'AGENT_ACCEPTANCE.json').exists():
                data=read(producer)
                if data.get('complete') and len(list((folder/'receipts').glob('*.json')))>=data['tasks']:
                    return dict(event='STAGE_COMPLETE_REQUIRES_ACCEPTANCE',stage=name,tasks=data['tasks'])
    legacy=BATCH2/'runs/batch3_compatibility_service_v1/failures'
    failures=list(legacy.glob('*.json'))
    if failures:return dict(event='COMPATIBILITY_SERVICE_FAILED',path=str(failures[0]),detail=read(failures[0]))
    cloud=BATCH2/'resources/CLOUD_LATEST.json'
    if cloud.exists():
        known={n['job'] for n in registry['nodes']}
        new=[v for v in read(cloud)['nodes'] if v['status']=='Running' and v['job'] in registry.get('pending_jobs',[]) and v['job'] not in known]
        if new:return dict(event='NEW_RUNNING_NODE_REQUIRES_PREFLIGHT',nodes=new)
    return None


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--interval',type=int,default=60);p.add_argument('--timeout',type=int,default=0);a=p.parse_args();began=time.monotonic()
    while True:
        event=inspect()
        if event:print(json.dumps(dict(time=stamp(),**event),ensure_ascii=False),flush=True);break
        if a.timeout and time.monotonic()-began>=a.timeout:
            print(json.dumps(dict(event='CHECKPOINT',time=stamp(),seconds=time.monotonic()-began)),flush=True);break
        time.sleep(a.interval)
