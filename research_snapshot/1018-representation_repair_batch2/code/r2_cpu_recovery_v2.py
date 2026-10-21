"""One verified exited CPU reader; retry only pre-claim inbox filesystem errors."""
from r2_common import *
import argparse


def main(args):
    assert args.job in socket.gethostname()
    folder = RUN/'cpu_recoveries'/args.worker
    folder.mkdir(parents=True, exist_ok=True)
    guard = (folder/'LOCK').open('a+')
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import r2_cpu
    original = r2_cpu.claim
    def bounded(kind, worker):
        for attempt in range(7):
            try:
                return original(kind, worker)
            except OSError as error:
                assert kind == 'cpu' and Path(error.filename) == RUN/'tasks_cpu.json'
                if error.errno not in {errno.ENOENT, errno.ESTALE, errno.EIO,
                                       errno.ETIMEDOUT, errno.EAGAIN}:
                    raise
                atomic(folder/'QUEUE_READ_RETRY.json', dict(time=stamp(), attempt=attempt+1,
                    error=repr(error), no_scientific_task_claimed=True))
                if attempt == 6:
                    raise
                time.sleep(min(.5*2**attempt, 8))
    r2_cpu.claim = bounded
    atomic(folder/'READY.json', dict(time=stamp(), hostname=socket.gethostname(),
        pid=os.getpid(), worker=args.worker, job=args.job, threads=args.threads,
        implementation=str(Path(__file__).relative_to(ROOT)), implementation_sha256=sha(Path(__file__)),
        original_cpu_source_sha256=sha(ROOT/'code/r2_cpu.py'),
        replacement_of_confirmed_exited=args.replaces, no_other_process_stopped=True))
    try:
        r2_cpu.main(args)
    except BaseException as error:
        import traceback
        atomic(RUN/'failures'/('cpu_recovery_'+args.worker+'.json'), dict(status='FAILED',
            time=stamp(), worker=args.worker, pid=os.getpid(), error=repr(error),
            traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--worker', required=True)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--job', required=True)
    p.add_argument('--replaces', required=True)
    main(p.parse_args())
