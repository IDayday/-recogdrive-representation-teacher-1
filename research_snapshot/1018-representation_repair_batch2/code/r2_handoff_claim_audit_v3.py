"""Read-only pending owner audit; never removes or requeues a claim."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor
import argparse


def main(a):
    workers=read(ROOT/'resources/handoffs/peer_b1_20261019/drain/WORKERS_BEFORE.json')['items']
    pids={w['process']['pid'] for w in workers};host='dlcqdtslnqnytsc7-'
    stages={s['path'] for s in read(ROOT/'config/GPU_STAGES.json')['stages']}
    specs=[(s,ROOT/s/'claims',ROOT/s/'receipts',ROOT/s/'failures') for s in sorted(stages)]
    specs.extend([('GLOBAL_CPU',RUN/'claims_cpu',RUN/'receipts_cpu',RUN/'failures_cpu'),
                  ('GLOBAL_RESIDENT_GPU',RUN/'claims_gpu',RUN/'receipts_gpu',RUN/'failures_gpu')])
    def scan(spec):
        stage,claims,receipts,failures=spec
        if not claims.exists():return dict(stage=stage,claims=0,pending=0,owned=[],empty=[])
        done={p.stem for p in receipts.glob('*.json')};names={p.name for p in claims.iterdir()} # Canonical protocol contains task directories only; avoid per-claim stat.
        owned=[];empty=[]
        for ident in names-done:
            p=claims/ident/'OWNER.json'
            try:owner=read(p)
            except FileNotFoundError:
                try:empty.append(dict(claim=str(p.parent.relative_to(ROOT)),mtime=p.parent.stat().st_mtime))
                except FileNotFoundError:pass
                continue
            if owner.get('pid') in pids and str(owner.get('hostname',owner.get('worker',''))).startswith(host):
                if (receipts/(ident+'.json')).exists():continue
                failure=failures/(ident+'.json');origin='current_stage'
                archived=ROOT/'provenance/superseded_failures'/(ident+'.json')
                if not failure.exists() and archived.exists():
                    historical=read(archived)
                    assert historical['status']=='FAILED' and historical['task']['id']==ident
                    assert historical['time']<read(ROOT/'resources/handoffs/peer_b1_20261019/drain/SUSPENDED_SAFE.json')['time']
                    failure=archived;origin='superseded_archive'
                owned.append(dict(stage=stage,claim=ident,owner=owner,
                    prior_failure_exists=failure.exists(),failure=str(failure.relative_to(ROOT)) if failure.exists() else None,
                    failure_sha256=sha(failure) if failure.exists() else None,failure_origin=origin,
                    resident_admission_wrapper=stage=='GLOBAL_RESIDENT_GPU'))
        return dict(stage=stage,claims=len(names),pending=len(names-done),owned=owned,empty=empty)
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda v:retry(lambda:scan(v)),specs))
    out=dict(time=stamp(),status='READONLY_CLAIM_OWNER_OBSERVATIONS',target_job='dlcqdtslnqnytsc7',
        exact_worker_pids=sorted(pids),stages_scanned=len(results),total_claims=sum(v['claims'] for v in results),
        target_pending=[x for v in results for x in v['owned']],empty_claim_observations=[x for v in results for x in v['empty']],
        scope='Concurrent other nodes may create or finish claims. Empty claims do not establish ownership. No deletion/requeue/termination performed.')
    atomic(ROOT/a.output,out)
    print(json.dumps(dict(output=a.output,stages=out['stages_scanned'],claims=out['total_claims'],
        target_pending=len(out['target_pending']),target_scientific_unfailed=sum(not x['resident_admission_wrapper'] and not x['prior_failure_exists'] for x in out['target_pending']),empty=len(out['empty_claim_observations']))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);main(p.parse_args())
