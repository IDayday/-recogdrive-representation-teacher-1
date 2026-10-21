"""Register a freshly preflighted Running node and append compatibility slots.

No cloud submission, worker launch, stop, or node release. The only batch-two
writes are the already authorized third-batch compatibility queue metadata.
Every scientific output stays under the third-batch task root.
"""
from r3_common import *
import argparse
import fcntl
import re


def mount_identity(line):
    values=line.split()
    # The fuse wrapper assigns a different rund handle in each container.
    return re.sub(r'^rund:[^:]+:','',values[0]),values[1]


def main(a):
    sys.path.insert(0,str(BATCH2/'code'))
    from r2_common import atomic as bridge_atomic
    folder=ROOT/'resources/nodes'/a.node;preflight=read(folder/'PREFLIGHT.json')
    assert preflight['status']=='PASS_ENVIRONMENT_NOT_MODEL_SMOKE' and preflight['job']==a.job and preflight['node']==a.node
    cloud=read(BATCH2/'resources/CLOUD_LATEST.json')
    age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds();assert age<300
    job=next(n for n in cloud['nodes'] if n['job']==a.job);assert job['status']=='Running'
    devices=[int(p['device']) for p in preflight['devices']];assert devices==list(range(len(devices)))
    if a.expected_devices is not None:assert len(devices)==a.expected_devices
    existing=read(ROOT/'resources/REGISTRY.json')
    reference=read(ROOT/existing['nodes'][0]['preflight'])
    for path in ['/mnt/workspace','/mnt/data','/mnt/yehr_workspace']:
        # Compare the source and target, then retain the full options for review.
        assert mount_identity(preflight['mounts'][path])==mount_identity(reference['mounts'][path]),path
    with (ROOT/'resources/COMPATIBILITY.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        registry_path=ROOT/'resources/REGISTRY.json';registry=read(registry_path)
        previous=[n for n in registry['nodes'] if n['name']==a.node or n['job']==a.job]
        if previous:
            assert len(previous)==1 and previous[0]['name']==a.node and previous[0]['job']==a.job and previous[0]['devices']==devices
        else:
            assert a.job in registry['pending_jobs']
            backup=folder/'REGISTRY_BEFORE_ADMISSION.json';assert not backup.exists();atomic(backup,registry)
            registry['nodes'].append(dict(name=a.node,job=a.job,devices=devices,preflight=str((folder/'PREFLIGHT.json').relative_to(ROOT))))
            registry['pending_jobs'].remove(a.job);registry['time']=stamp();atomic(registry_path,registry)
        stage=BATCH2/'runs/batch3_compatibility_service_v1';tasks_path=stage/'tasks.json';producer_path=stage/'producer.json'
        tasks=read(tasks_path);producer=read(producer_path);old_ids={v['id'] for v in tasks}
        source=ROOT/'code/r3_resident_service_v1.py'
        appended=[dict(id='r3_service_slot_'+a.node+'_%03d'%d,third_batch_handler=str(source.relative_to(ROOT)),third_batch_handler_sha256=sha(source))
                  for d in devices if 'r3_service_slot_'+a.node+'_%03d'%d not in old_ids]
        if appended:
            backup=folder/'COMPATIBILITY_BEFORE_ADMISSION.json';assert not backup.exists()
            atomic(backup,dict(tasks=tasks,producer=producer))
            bridge_atomic(tasks_path,tasks+appended)
            bridge_atomic(producer_path,dict(producer,time=stamp(),tasks=len(tasks)+len(appended)))
        record=dict(status='REGISTERED_PREFLIGHT_ONLY_MODEL_ADMISSION_PENDING',time=stamp(),node=a.node,job=a.job,devices=devices,
                    appended_slots=len(appended),preflight_sha256=sha(folder/'PREFLIGHT.json'),compatibility_tasks_sha256=sha(tasks_path),
                    registry_sha256=sha(registry_path),cloud_snapshot_time=cloud['time'],no_cloud_or_process_mutations=True)
        atomic(folder/'COMPATIBILITY_ADMISSION.json',record)
    print(json.dumps(record),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--job',required=True);p.add_argument('--expected-devices',type=int);main(p.parse_args())
