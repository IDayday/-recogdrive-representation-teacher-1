"""Task-scoped CPU queue with immutable per-task handler identities."""
from r2_common import *
import argparse
import importlib.util
import traceback


def main(args):
    setup('cpu/' + args.worker, args.threads)
    compatibility()
    from threadpoolctl import threadpool_limits
    cache = {}
    with threadpool_limits(args.threads):
        while True:
            task = claim('cpu', args.worker)
            status = RUN / 'workers_cpu' / (args.worker + '.json')
            if task is None:
                atomic(status, dict(status='QUEUE_WAIT', time=stamp())); time.sleep(15); continue
            began = time.monotonic()
            atomic(status, dict(status='COMPUTING', time=stamp(), task=task['id']))
            try:
                source = (ROOT / task['handler']).resolve()
                assert source.is_relative_to(ROOT / 'code') and sha(source) == task['handler_sha256']
                key = task['handler_sha256']
                if key not in cache:
                    spec = importlib.util.spec_from_file_location('r2_cpu_handler_' + key, source)
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); cache[key] = module
                value = cache[key].run(task)
                atomic(RUN / 'receipts_cpu' / (task['id'] + '.json'), dict(status='COMPLETE',
                       time=stamp(), worker=args.worker, task=task, seconds=time.monotonic()-began, result=value))
            except BaseException as error:
                atomic(RUN / 'failures_cpu' / (task['id'] + '.json'), dict(status='FAILED',
                       time=stamp(), worker=args.worker, task=task, error=repr(error), traceback=traceback.format_exc()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--worker', required=True)
    p.add_argument('--threads', type=int, default=2); main(p.parse_args())
