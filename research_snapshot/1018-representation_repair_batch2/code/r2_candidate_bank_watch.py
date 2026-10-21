"""Mechanical candidate cache reductions, once each complete policy point."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set();base=ROOT/'runs/candidate_selector_cv_v1'
    while True:
        receipts={p.stem for p in (base/'receipts').glob('*.json')};tasks=[]
        for path in (base/'points').glob('*.json'):
            point=read(path);ident='outcome_candidate_bank_'+digest(dict(stage=str(base),point=point['id']))[:24]
            if ident in queued:continue
            chunks=[point['id']+'_%04d'%start for start in range(0,len(point['panel']),4)]
            if all(c in receipts for c in chunks):tasks.append(dict(id=ident,handler='code/r2_candidate_bank_matrix.py',handler_sha256=sha(ROOT/'code/r2_candidate_bank_matrix.py'),stage=str(base.relative_to(ROOT)),point=str(path.relative_to(ROOT)),chunks=chunks));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/candidate_banks/PRODUCER.json',dict(time=stamp(),points_queued=len(queued)))
        time.sleep(60)


if __name__=='__main__':main()
