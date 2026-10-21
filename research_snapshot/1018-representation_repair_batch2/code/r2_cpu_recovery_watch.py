"""Read-only local liveness for one manually verified replacement CPU process."""
from r2_common import *
import argparse


def main(args):
    import psutil
    ready=read(RUN/'cpu_recoveries'/args.worker/'READY.json');assert ready['job'] in socket.gethostname()
    folder=RUN/'cpu_recoveries'/args.worker;guard=(folder/'HEALTH_LOCK').open('a+');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    process=psutil.Process(ready['pid']);created=process.create_time()
    while True:
        try:
            assert process.is_running() and process.create_time()==created and process.status()!=psutil.STATUS_ZOMBIE
            cmd=process.cmdline();assert str(ROOT/'code/r2_cpu_recovery_v1.py') in cmd and args.worker in cmd
            atomic(folder/'HEALTH.json',dict(time=stamp(),pid=ready['pid'],status='PROCESS_RUNNING',identity_verified=True,automatic_restart=False))
        except BaseException as error:
            atomic(RUN/'failures'/('cpu_recovery_watch_'+args.worker+'.json'),dict(status='RECOVERED_CPU_PROCESS_ATTENTION',time=stamp(),worker=args.worker,pid=ready['pid'],error=repr(error),no_resource_action=True));return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',required=True);main(p.parse_args())
