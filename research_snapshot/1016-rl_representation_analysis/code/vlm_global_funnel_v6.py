"""Keep frozen V5 science; inspect only fixed error directories while waiting."""
from common import *
import fcntl, traceback
import vlm_global_funnel_v5 as original
from vlm_core import VOUT
from vlm_event_watch_v2 import errors
from repair_queue_v2 import atomic_unique as atomic


def wait_stage(name):
    while True:
        source = original.BASE if (original.BASE/'stages'/name/'PROTOCOL.json').exists() else ROOT/'runs/vlm_repair_20261016_v2'
        if (source/'stages'/name/'PROTOCOL.json').exists():
            result = original.summarize(source, name)
            if result is not None:
                return result
        failed = errors()
        if failed:
            raise RuntimeError('Original failure '+str(failed[0]))
        time.sleep(30)


def main():
    setup('vlm_repair/global_funnel_v6')
    execution = read(VOUT/'CONTROLLER_RECOVERY_EXECUTION.json')
    for p, h in execution['code_sha256'].items():
        assert sha(ROOT/p) == h, p
    original.G.mkdir(exist_ok=True)
    with (original.G/'controller_v6.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # No numeric, candidate, stage, gate, seed or evaluation code changes.
        original.wait_stage = wait_stage
        original.main()


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        atomic(VOUT/'failures/global_funnel_v6.json', dict(status='FAILED', time=stamp(), error=repr(exc), traceback=traceback.format_exc()))
        raise
