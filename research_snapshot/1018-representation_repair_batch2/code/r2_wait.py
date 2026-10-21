"""Mechanical completion/error wait. No scientific decisions or resource release."""
from r2_common import *
import argparse


def main(args):
    began=time.monotonic()
    while True:
        done={p.stem for p in (RUN/('receipts_'+args.kind)).glob(args.prefix+'*.json')}
        failures=list((RUN/('failures_'+args.kind)).glob('*.json'))
        node_failures=list((RUN/'failures').glob('*.json'))
        if failures or node_failures:
            print(json.dumps(dict(status='ERROR',time=stamp(),completed=len(done),
                  failures=[str(p.relative_to(ROOT)) for p in failures+node_failures][:20])),flush=True)
            return 2
        if len(done)>=args.expected:
            print(json.dumps(dict(status='COMPLETE',time=stamp(),kind=args.kind,prefix=args.prefix,
                  completed=len(done),seconds=time.monotonic()-began)),flush=True)
            return 0
        if args.timeout and time.monotonic()-began>args.timeout:
            print(json.dumps(dict(status='TIMEOUT',time=stamp(),completed=len(done))),flush=True)
            return 3
        time.sleep(args.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['cpu','gpu'],required=True)
    p.add_argument('--prefix',default='');p.add_argument('--expected',type=int,required=True)
    p.add_argument('--interval',type=int,default=60);p.add_argument('--timeout',type=int,default=0)
    raise SystemExit(main(p.parse_args()))
