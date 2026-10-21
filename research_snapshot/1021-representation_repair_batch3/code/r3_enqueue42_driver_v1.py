"""Append configurable leases and independent all-quality scientific work items."""
from r3_common import *
import argparse
import fcntl


def main(a):
    rows=Path(a.rows);data=read(rows);pack=ROOT/'manifests/first42_v1.json';pack_sha=sha(pack);rows_sha=sha(rows)
    stage=ROOT/'runs'/a.stage;assert not stage.exists()
    indices=[int(v) for v in a.indices.split(',')] if a.indices else list(range(len(data) if a.full else a.cases))
    assert len(indices)==len(set(indices)) and all(0<=i<len(data) for i in indices)
    if a.cohort=='navtest':
        lock=read(ROOT/'provenance/FIRST42_TEST_LOCK.json');assert lock['pack_sha256']==pack_sha and lock['test_rows_sha256']==rows_sha
        if not a.engineering:assert (ROOT/'runs/first42_navtrain_v1/AGENT_ACCEPTANCE.json').exists()
    assert a.engineering or a.full
    tasks=[dict(id=a.stage+'_%06d'%offset,stage=str(stage.relative_to(ROOT)),indices=indices[offset:offset+a.chunk_size],
                rows=str(rows),rows_sha256=rows_sha,pack=str(pack),pack_sha256=pack_sha,seeds=[0,1,2,3,4],cohort=a.cohort)
           for offset in range(0,len(indices),a.chunk_size)]
    atomic(stage/'tasks.json',tasks);worklist_sha=sha(stage/'tasks.json')
    evaluation=ROOT/'code/r3_first42_rollout_v2.py';driver=ROOT/'code/r3_first42_driver_v1.py'
    atomic(stage/'producer.json',dict(complete=True,time=stamp(),tasks=len(tasks),cases=len(indices),seeds=[0,1,2,3,4],entries=42,
                                    cohort=a.cohort,rows=str(rows),rows_sha256=rows_sha,pack_sha256=pack_sha,worklist_sha256=worklist_sha,
                                    evaluation_sha256=sha(evaluation),engineering=a.engineering,chunk_size=a.chunk_size))
    leases=ROOT/'runs'/(a.stage+'_leases');assert not leases.exists()
    records=[dict(id=a.stage+'_lease%03d'%i,stage=str(leases.relative_to(ROOT)),handler=str(driver.relative_to(ROOT)),handler_sha256=sha(driver),
                  work_stage=str(stage.relative_to(ROOT)),worklist_sha256=worklist_sha,evaluation_sha256=sha(evaluation)) for i in range(a.leases)]
    atomic(leases/'tasks.json',records);atomic(leases/'producer.json',dict(complete=True,time=stamp(),tasks=len(records),work_stage=str(stage.relative_to(ROOT))))
    with (ROOT/'runs/QUEUE.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);queue=ROOT/'runs/QUEUE.json';old=read(queue) if queue.exists() else dict(tasks=[])
        assert not {v['id'] for v in old['tasks']}.intersection(v['id'] for v in records)
        old['tasks'].extend(records);old['time']=stamp();atomic(queue,old)
    print(json.dumps(dict(stage=str(stage.relative_to(ROOT)),tasks=len(tasks),cases=len(indices),leases=len(records),entries=42,seeds=5)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--rows',default=str(BATCH1/'manifests/natural_s0.json'));p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain')
    p.add_argument('--full',action='store_true');p.add_argument('--cases',type=int,default=64);p.add_argument('--indices');p.add_argument('--chunk-size',type=int,default=2)
    p.add_argument('--leases',type=int,default=80);p.add_argument('--engineering',action='store_true');main(p.parse_args())
