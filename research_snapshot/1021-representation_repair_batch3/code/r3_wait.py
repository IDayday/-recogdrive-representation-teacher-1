"""Mechanical completion/failure/node-change waiter; no scientific decisions."""
from r3_common import *
import argparse


def main(args):
    watched=[Path(p) if Path(p).is_absolute() else ROOT/p for p in args.until]
    failed=[Path(p) if Path(p).is_absolute() else ROOT/p for p in args.failure]
    began=time.monotonic()
    while True:
        for path in failed:
            if path.exists():
                print(json.dumps(dict(event='FAILURE_REQUIRES_REVIEW',path=str(path),detail=read(path)),ensure_ascii=False),flush=True);return 3
        ready=[str(p) for p in watched if p.exists()]
        if len(ready)==len(watched):
            print(json.dumps(dict(event='STAGE_COMPLETE_REQUIRES_ACCEPTANCE',files=ready,seconds=time.monotonic()-began)),flush=True);return 0
        if args.timeout and time.monotonic()-began>=args.timeout:
            print(json.dumps(dict(event='CHECKPOINT',ready=ready,pending=[str(p) for p in watched if not p.exists()],seconds=time.monotonic()-began)),flush=True);return 2
        time.sleep(args.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--until',action='append',required=True);p.add_argument('--failure',action='append',default=[])
    p.add_argument('--interval',type=int,default=60);p.add_argument('--timeout',type=int,default=0)
    raise SystemExit(main(p.parse_args()))
