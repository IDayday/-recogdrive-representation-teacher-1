"""Tool-owned wait for a stage milestone, completion, or first recorded error."""
from r2_common import *
import argparse


def main(args):
    base=(ROOT/args.stage).resolve();assert base.is_relative_to(ROOT)
    began=time.monotonic()
    while True:
        failures=list((base/'failures').glob('*.json'))+list((RUN/'failures_gpu').glob('*.json'))+list((RUN/'failures_cpu').glob('*.json'))
        if failures:
            print(json.dumps(dict(status='ERROR',time=stamp(),failures=[str(p.relative_to(ROOT)) for p in failures][:20])),flush=True);return 2
        done=len(list((base/'receipts').glob('*.json')))
        producer=read(base/'producer.json') if (base/'producer.json').exists() else {}
        if args.minimum and done>=args.minimum:
            print(json.dumps(dict(status='MILESTONE',time=stamp(),completed=done,stage=args.stage,seconds=time.monotonic()-began)),flush=True);return 0
        if producer.get('complete') and done>=producer['tasks']:
            print(json.dumps(dict(status='COMPLETE',time=stamp(),completed=done,stage=args.stage,seconds=time.monotonic()-began)),flush=True);return 0
        time.sleep(args.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--minimum',type=int,default=0)
    p.add_argument('--interval',type=int,default=60);raise SystemExit(main(p.parse_args()))
