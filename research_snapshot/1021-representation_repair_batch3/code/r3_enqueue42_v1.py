"""Configurable independent chunks; candidate/test identity frozen by pack hash."""
from r3_common import *
import argparse
import fcntl


def main(a):
    pack=ROOT/'manifests/first42_v1.json';assert len(read(pack)['entries'])==42
    stage=ROOT/'runs'/a.stage;assert not stage.exists()
    rows=Path(a.rows);data=read(rows);size=len(data)
    indices=[int(v) for v in a.indices.split(',')] if a.indices else list(range(size if a.full else a.cases))
    assert len(indices)==len(set(indices)) and all(0<=i<size for i in indices)
    if a.cohort=='navtest':
        assert a.full or a.engineering
        assert (ROOT/'provenance/FIRST42_TEST_LOCK.json').exists()
    handler=ROOT/'code/r3_first42_rollout_v1.py';handler_sha=sha(handler);rows_sha=sha(rows);pack_sha=sha(pack);tasks=[]
    for offset in range(0,len(indices),a.chunk_size):
        tasks.append(dict(id=a.stage+'_%06d'%offset,stage=str(stage.relative_to(ROOT)),handler=str(handler.relative_to(ROOT)),handler_sha256=handler_sha,
                          rows=str(rows),rows_sha256=rows_sha,pack=str(pack),pack_sha256=pack_sha,indices=indices[offset:offset+a.chunk_size],seeds=[0,1,2,3,4],cohort=a.cohort))
    atomic(stage/'tasks.json',tasks)
    atomic(stage/'producer.json',dict(time=stamp(),complete=True,tasks=len(tasks),cases=len(indices),seeds=[0,1,2,3,4],entries=42,pack_sha256=pack_sha,handler_sha256=handler_sha,
                                   cohort=a.cohort,engineering=a.engineering,chunk_size=a.chunk_size))
    with (ROOT/'runs/QUEUE.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);queue=ROOT/'runs/QUEUE.json';old=read(queue) if queue.exists() else dict(tasks=[])
        assert not {t['id'] for t in old['tasks']}.intersection(t['id'] for t in tasks)
        old['tasks'].extend(tasks);old['time']=stamp();atomic(queue,old)
    print(json.dumps(dict(stage=str(stage.relative_to(ROOT)),cases=len(indices),tasks=len(tasks),seeds=5,entries=42)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--rows',default=str(BATCH1/'manifests/natural_s0.json'));p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain')
    p.add_argument('--full',action='store_true');p.add_argument('--cases',type=int,default=2);p.add_argument('--indices');p.add_argument('--chunk-size',type=int,default=2);p.add_argument('--engineering',action='store_true');main(p.parse_args())
