"""One mechanical wake-up at a configured age of the first actual task claim."""
from r2_common import *
import argparse


def main(args):
    setup('first_claim_phase_watch')
    stage=(ROOT/args.stage).resolve();output=(ROOT/args.output).resolve()
    assert stage.is_relative_to(ROOT/'runs') and output.is_relative_to(ROOT)
    assert 60<=args.seconds<=3600
    while not output.exists():
        owners=[]
        for path in (stage/'claims').glob('*/OWNER.json'):
            value=read(path)
            if value.get('time'):owners.append(value)
        if owners:
            first=min(owners,key=lambda v:v['time']);elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(first['time'])).total_seconds()
            if elapsed>=args.seconds:
                atomic(output,dict(time=stamp(),stage=args.stage,first_actual_claim=first,elapsed_seconds=elapsed,mechanical_phase_flag_only=True,no_resource_action=True));return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--output',required=True);p.add_argument('--seconds',type=int,default=300)
    main(p.parse_args())
