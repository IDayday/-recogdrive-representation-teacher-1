"""One-shot mechanical timer from a task's actual START record; no resource actions."""
from r2_common import *
import argparse


def main(args):
    setup('elapsed_file_watch_v1')
    source=(ROOT/args.source).resolve();output=(ROOT/args.output).resolve()
    assert source.is_relative_to(ROOT) and output.is_relative_to(ROOT)
    assert 60<=args.seconds<=432000
    while not output.exists():
        if source.exists():
            record=read(source)
            elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(record['time'])).total_seconds()
            if elapsed>=args.seconds:
                atomic(output,dict(time=stamp(),status='READY_FOR_AGENT_PHASE_REVIEW',source=args.source,
                    source_sha256=sha(source),elapsed_seconds=elapsed,no_automatic_action=True))
                return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=int,default=300);main(p.parse_args())
