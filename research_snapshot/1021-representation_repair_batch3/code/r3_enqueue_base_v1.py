"""Append independent Base work; shared queues stay open and restart-safe."""
from r3_common import *
import argparse
import fcntl


def main(a):
    stage=ROOT/'runs'/a.stage;assert not stage.exists();rows=BATCH1/'manifests/natural_s0.json';data=read(rows)
    assert len(data)==103288 and len({r['token'] for r in data})==len(data)
    assert all(r['subset'] in ['exploration','validation'] for r in data)
    size=len(data) if a.full else a.cases;assert 1<=size<=len(data)
    handler=ROOT/'code/r3_base_rollout_v1.py';tasks=[]
    for start in range(0,size,a.chunk_size):
        tasks.append(dict(id=a.stage+'_%06d'%start,stage=str(stage.relative_to(ROOT)),handler=str(handler.relative_to(ROOT)),handler_sha256=sha(handler),
                          rows=str(rows),rows_sha256=sha(rows),start=start,end=min(start+a.chunk_size,size),seeds=[0,1,2,3,4]))
    atomic(stage/'tasks.json',tasks);atomic(stage/'producer.json',dict(time=stamp(),complete=True,tasks=len(tasks),cases=size,seeds=[0,1,2,3,4],mode='full' if a.full else 'engineering',chunk_size=a.chunk_size))
    lock=ROOT/'runs/QUEUE.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);queue=ROOT/'runs/QUEUE.json';old=read(queue) if queue.exists() else dict(tasks=[])
        assert not {t['id'] for t in old['tasks']}.intersection(t['id'] for t in tasks)
        old['tasks'].extend(tasks);old['time']=stamp();atomic(queue,old)
    print(json.dumps(dict(stage=str(stage.relative_to(ROOT)),cases=size,tasks=len(tasks),seeds=5)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--full',action='store_true');p.add_argument('--cases',type=int,default=64);p.add_argument('--chunk-size',type=int,default=4)
    main(p.parse_args())
