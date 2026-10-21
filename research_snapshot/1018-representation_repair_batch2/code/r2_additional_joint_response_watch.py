"""Mechanical reduction of complete policy points across append-only stages."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set();stages=['additional_joint_quick_v1','additional_joint_policy_cv_v1']
    while True:
        tasks=[]
        for name in stages:
            base=ROOT/'runs'/name
            receipts={p.stem for p in (base/'receipts').glob('*.json')}
            for path in (base/'points').glob('*.json'):
                point=read(path);ident='outcome_policy_matrix_'+digest(dict(stage=name,point=point['id']))[:24]
                if ident in queued:continue
                chunks=[point['id']+'_%04d'%start for start in range(0,len(point['panel']),4)]
                if all(c in receipts for c in chunks):
                    tasks.append(dict(id=ident,handler='code/r2_policy_response.py',handler_sha256=sha(ROOT/'code/r2_policy_response.py'),stage=str(base.relative_to(ROOT)),point=str(path.relative_to(ROOT)),chunks=chunks));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/additional_joint_policy_responses/PRODUCER.json',dict(time=stamp(),complete_points_queued=len(queued),stages=stages))
        time.sleep(60)


if __name__=='__main__':main()
