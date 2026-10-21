"""Append scheduling capacity without changing any scientific work item."""
from r3_common import *
import argparse
import fcntl


def main(a):
    stage=ROOT/'runs'/a.stage;leases=ROOT/'runs'/(a.stage+'_leases');producer=read(stage/'producer.json');records=read(leases/'tasks.json');before=len(records)
    assert before<a.total and all(t['work_stage']==str(stage.relative_to(ROOT)) for t in records)
    prototype=records[0];extra=[dict(prototype,id=a.stage+'_lease%03d'%i) for i in range(before,a.total)]
    assert sha(stage/'tasks.json')==prototype['worklist_sha256'] and sha(ROOT/'code/r3_first42_rollout_v2.py')==prototype['evaluation_sha256']
    with (ROOT/'runs/QUEUE.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);queue=read(ROOT/'runs/QUEUE.json')
        assert not {t['id'] for t in queue['tasks']}.intersection(t['id'] for t in extra)
        atomic(leases/'tasks.json',records+extra);p=read(leases/'producer.json');p.update(tasks=a.total,time=stamp(),scheduling_only_expansion=True);atomic(leases/'producer.json',p)
        queue['tasks'].extend(extra);queue['time']=stamp();atomic(ROOT/'runs/QUEUE.json',queue)
    proof=dict(time=stamp(),before=before,after=a.total,scientific_worklist_sha256=sha(stage/'tasks.json'),scientific_evaluation_sha256=prototype['evaluation_sha256'],
               no_candidate_or_model_or_noise_or_output_changes=True)
    atomic(leases/('EXPANSION_%03d.json'%a.total),proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--total',type=int,required=True);main(p.parse_args())
