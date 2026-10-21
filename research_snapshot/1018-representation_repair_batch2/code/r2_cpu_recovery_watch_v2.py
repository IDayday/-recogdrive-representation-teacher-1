"""Read-only process identity/health for the independently recovered CPU reader."""
from r2_common import *
import argparse


def main(worker):
    import psutil
    folder = RUN/'cpu_recoveries'/worker
    ready = read(folder/'READY.json')
    assert ready['job'] in socket.gethostname()
    guard = (folder/'HEALTH_LOCK').open('a+')
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    process = psutil.Process(ready['pid'])
    created = process.create_time()
    while True:
        try:
            assert process.is_running() and process.create_time() == created
            assert process.status() != psutil.STATUS_ZOMBIE
            assert str(ROOT/ready['implementation']) in process.cmdline()
            assert worker in process.cmdline()
            atomic(folder/'HEALTH.json', dict(time=stamp(), pid=ready['pid'],
                status='PROCESS_RUNNING', identity_verified=True, automatic_restart=False))
        except BaseException as error:
            atomic(RUN/'failures'/('cpu_recovery_watch_'+worker+'.json'),
                dict(status='RECOVERED_CPU_PROCESS_ATTENTION', time=stamp(),
                     worker=worker, pid=ready['pid'], error=repr(error), no_resource_action=True))
            return
        time.sleep(60)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--worker', required=True)
    main(p.parse_args().worker)
