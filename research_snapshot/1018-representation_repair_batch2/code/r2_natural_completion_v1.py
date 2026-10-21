"""Mechanical completion/reduction of an already frozen natural experiment.

Never selects a policy, starts test inference, mutates a worker, or releases a job.
"""
from r2_common import *
import argparse


def main(args):
    setup('natural_completion/'+args.name,threads=8)
    stage=(ROOT/args.stage).resolve();assert stage.is_relative_to(ROOT/'runs')
    tasks=read(stage/'tasks.json');expected={t['id'] for t in tasks};assert expected
    folder=stage/'completion_monitor';folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'COMPLETE.json').exists()
    while True:
        failures=list((stage/'failures').glob('*.json'))
        if failures:raise RuntimeError('Frozen stage failure: '+str(failures[0].relative_to(ROOT)))
        receipts={p.stem:p for p in (stage/'receipts').glob('*.json') if p.stem in expected}
        if receipts and not (folder/'START.json').exists():
            first=min(receipts.values(),key=lambda p:p.stat().st_mtime_ns)
            record=read(first)
            atomic(folder/'START.json',dict(time=record['time'],first_receipt=str(first.relative_to(ROOT)),
                expected_chunks=len(expected),no_automatic_experimental_decision=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),complete=len(receipts),expected=len(expected),
            mode=args.mode,no_resource_action=True))
        if receipts and (folder/'START.json').exists() and not (folder/'FIRST_PHASE_READY.json').exists():
            elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(read(folder/'START.json')['time'])).total_seconds()
            if elapsed>=300:
                atomic(folder/'FIRST_PHASE_READY.json',dict(time=stamp(),elapsed_seconds=elapsed,
                    complete_chunks=len(receipts),requires_actual_output_review=True))
        if set(receipts)==expected:break
        time.sleep(60)
    from r2_natural_assessment_shared_spec import run as assess
    from r2_confirmation_statistics import run as statistics
    from r2_natural_stability import run as stability
    result=assess(dict(id=args.name+'_assessment',stage=args.stage,bootstrap_samples=2000))
    summary=result['path']
    uncertainty=statistics(dict(id=args.name+'_statistics',assessment=summary,
        bootstrap_samples=10000,permutation_samples=19999))
    strata=stability(dict(id=args.name+'_stability',assessment=summary,bootstrap_samples=2000))
    record=dict(status='COMPLETE_FROZEN_NATURAL_STAGE',time=stamp(),mode=args.mode,
        stage=args.stage,assessment=result,statistics=uncertainty,stability=strata,
        no_policy_reselection=True,no_automatic_test_or_resource_action=True,
        source_sha256=sha(Path(__file__)))
    atomic(folder/'COMPLETE.json',record)
    print(json.dumps(record),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True)
    p.add_argument('--name',required=True);p.add_argument('--mode',choices=['validation','test'],required=True)
    main(p.parse_args())
