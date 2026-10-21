"""Single task-local cloud reader surviving DSW terminal interruptions."""
from r2_common import *


if __name__=='__main__':
    setup('resource_monitor_guard')
    folder=ROOT/'resources/cloud_monitor_guard'
    folder.mkdir(parents=True,exist_ok=True)
    guard=(folder/'LOCK').open('a+')
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    import psutil
    process=psutil.Process()
    atomic(folder/'READY.json',dict(time=stamp(),pid=os.getpid(),created=process.create_time(),
        cmdline=process.cmdline(),uid=os.getuid(),hostname=socket.gethostname(),
        original_monitor_sha256=sha(ROOT/'code/r2_resources.py'),
        no_scientific_or_environment_change=True))
    import r2_resources
    try:
        code=r2_resources.main()
        atomic(folder/'EXIT.json',dict(time=stamp(),exit_code=code,no_automatic_restart=True))
        raise SystemExit(code)
    except Exception as error:
        import traceback
        atomic(folder/'FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
