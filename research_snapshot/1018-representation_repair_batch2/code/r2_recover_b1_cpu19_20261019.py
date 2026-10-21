"""Run inside B1: restore one confirmed exited, idle CPU queue reader."""
from r2_common import *
import subprocess


def main():
    setup('recover_b1_cpu19')
    import psutil
    name, job, old, new = 'peer_b1', 'dlcqdtslnqnytsc7', 'peer_b1_cpu19', 'peer_b1_cpu19_recovery1'
    assert socket.gethostname().startswith(job)
    node = next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name'] == name)
    assert node['active_for_batch2'] and len(node['devices']) == 16
    live = read(RUN/'nodes'/name/'LIVE.json')
    assert live['pid'] == 296157
    assert live['children'][old] == dict(pid=296180, returncode=1)
    assert not psutil.pid_exists(296180), 'Old PID must remain absent, not be signaled'
    assert read(RUN/'workers_cpu'/f'{old}.json')['status'] == 'QUEUE_WAIT'
    logfile = RUN/'nodes'/name/f'{old}.log'
    log = logfile.read_text()
    assert "[Errno 116] Stale file handle" in log and "if not path.exists(): return None" in log
    assert str(RUN/'tasks_cpu.json') in log
    inbox = read(RUN/'tasks_cpu.json')
    assert isinstance(inbox, list)
    folder = ROOT/'provenance/cpu_recoveries'/new
    folder.mkdir(parents=True, exist_ok=True)
    assert not (RUN/'cpu_recoveries'/new/'READY.json').exists()
    evidence = dict(time=stamp(), old_live=live['children'][old], old_parent_pid=live['pid'],
        old_log_sha256=sha(logfile), old_status=read(RUN/'workers_cpu'/f'{old}.json'),
        failure_before_claim=True, original_cpu_sha256=sha(ROOT/'code/r2_cpu.py'))
    atomic(folder/'BEFORE.json', evidence)
    with (folder/'worker.log').open('a') as stream:
        child = subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/r2_cpu_recovery_v2.py'),
            '--worker',new,'--threads',str(node['cpu_threads']),'--job',job,'--replaces',old],
            cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(30):
        if (RUN/'cpu_recoveries'/new/'READY.json').exists(): break
        assert child.poll() is None
        time.sleep(.5)
    ready=read(RUN/'cpu_recoveries'/new/'READY.json')
    assert ready['pid'] == child.pid and ready['original_cpu_source_sha256'] == evidence['original_cpu_sha256']
    with (folder/'health.log').open('a') as stream:
        watcher = subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/r2_cpu_recovery_watch_v2.py'),
            '--worker',new], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(30):
        if (RUN/'cpu_recoveries'/new/'HEALTH.json').exists(): break
        assert watcher.poll() is None
        time.sleep(.5)
    health=read(RUN/'cpu_recoveries'/new/'HEALTH.json')
    assert health['identity_verified'] and child.poll() is None
    atomic(folder/'ACCEPTANCE.json', dict(status='RECOVERY_READY_AND_MONITORED', time=stamp(),
        ready=ready, health=health, watcher_pid=watcher.pid, original_source_and_failure_preserved=True,
        no_process_stopped=True, no_node_release=True, no_environment_change=True,
        scope='Only one exited idle CPU reader replaced. Before-claim ESTALE preserved; '
              'original source/handlers/tasks/claimed work unchanged.'))
    print(json.dumps(dict(status='PASS', worker=new, pid=child.pid, watcher_pid=watcher.pid)), flush=True)


if __name__ == '__main__':
    main()
