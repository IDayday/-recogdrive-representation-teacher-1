"""Whole-point finite-outcome matrices and a metadata-only review projection."""
from r2_common import *
from r2_resume_support import append_once


def main():
    stage=ROOT/'runs/finite_outcome_router_cv_v1';queued=set();projected=set()
    while True:
        receipts={p.stem for p in (stage/'receipts').glob('*.json')};work=[]
        for path in (stage/'points').glob('*.json'):
            point=read(path);ident='outcome_finite_router_matrix_'+digest(dict(point=point['id']))[:24];chunks=[point['id']+'_%04d'%j for j in range(0,len(point['panel']),4)]
            if ident not in queued and all(c in receipts for c in chunks):work.append(dict(id=ident,handler='code/r2_policy_response.py',handler_sha256=sha(ROOT/'code/r2_policy_response.py'),stage=str(stage.relative_to(ROOT)),point=str(path.relative_to(ROOT)),chunks=chunks));queued.add(ident)
            result=ROOT/'analysis/responses/finite_outcome_router_cv_v1'/path.name
            if point['id'] not in projected and result.exists():
                original=read(result);alias=ROOT/'analysis/responses/token_full_cv_projection_v1'/('finite_'+path.name)
                atomic(alias,dict(original,projection_kind='finite_outcome_policy',original_response=str(result.relative_to(ROOT)),metadata_only_projection=True));projected.add(point['id'])
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/finite_outcome_router_cv/PRODUCER.json',dict(time=stamp(),matrices_queued=len(queued),projected=len(projected)))
        time.sleep(60)


if __name__=='__main__':main()
