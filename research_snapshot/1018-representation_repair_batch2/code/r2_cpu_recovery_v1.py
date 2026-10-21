"""Replace one confirmed exited task CPU worker, retaining all old evidence.

Only a missing, previously verified CPU inbox at claim-time gets bounded retries.
No handler mathematics, already owned tasks, environment or other process changes.
"""
from r2_common import *
import argparse


def main(args):
    assert args.job in socket.gethostname()
    folder=RUN/'cpu_recoveries'/args.worker;folder.mkdir(parents=True,exist_ok=True)
    guard=(folder/'LOCK').open('a+');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    import r2_cpu
    original=r2_cpu.claim
    def bounded(kind,worker):
        for attempt in range(7):
            try:return original(kind,worker)
            except FileNotFoundError as error:
                assert kind=='cpu' and Path(error.filename)==RUN/'tasks_cpu.json'
                atomic(folder/'QUEUE_READ_RETRY.json',dict(time=stamp(),attempt=attempt+1,path=str(error.filename),error=repr(error),no_scientific_task_claimed=True))
                if attempt==6:raise
                time.sleep(min(.5*2**attempt,8))
    r2_cpu.claim=bounded
    atomic(folder/'READY.json',dict(time=stamp(),hostname=socket.gethostname(),pid=os.getpid(),worker=args.worker,job=args.job,threads=args.threads,
        original_cpu_source_sha256=sha(ROOT/'code/r2_cpu.py'),replacement_of_confirmed_exited='peer_b2_cpu13',no_other_process_stopped=True))
    try:r2_cpu.main(args)
    except BaseException as error:
        import traceback
        atomic(RUN/'failures'/('cpu_recovery_'+args.worker+'.json'),dict(status='FAILED',time=stamp(),worker=args.worker,pid=os.getpid(),error=repr(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',required=True);p.add_argument('--threads',type=int,default=2);p.add_argument('--job',required=True);main(p.parse_args())
