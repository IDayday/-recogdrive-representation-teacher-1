"""Per-node batch-two supervision, configurable cards, retained parent process."""
from r2_common import *
import argparse
import subprocess
import traceback


def main(name):
    setup('nodes/' + name)
    import psutil
    node = next(n for n in read(ROOT / 'resources/NODES.json')['nodes'] if n['name'] == name)
    assert socket.gethostname().startswith(node['job'])
    directory = RUN / 'nodes' / name; directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'node.lock').open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        mounts = {path: subprocess.check_output(['findmnt', '-T', path, '-n', '-o',
                  'SOURCE,TARGET,FSTYPE,OPTIONS'], text=True).strip()
                  for path in ['/mnt/workspace', '/mnt/data', '/mnt/yehr_workspace']}
        assert len(os.sched_getaffinity(0)) >= 16 and psutil.virtual_memory().available > 64 * 1024**3
        atomic(directory / 'PREFLIGHT.json', dict(status='PASS', time=stamp(), node=node,
               hostname=socket.gethostname(), mounts=mounts, memory_available=psutil.virtual_memory().available,
               cpu_affinity=len(os.sched_getaffinity(0)), independent_main=True, no_old_process_stopped=True))
        processes = {}; streams = []
        for device in node['devices']:
            if (RUN / 'smoke' / name / f'device{device:02d}.json').exists(): continue
            stream = (directory / f'smoke_device{device:02d}.log').open('a'); streams.append(stream)
            rank = node['rank_base'] + device
            processes[f'smoke_{device}'] = subprocess.Popen([sys.executable, '-u', '-B',
                str(ROOT / 'code/r2_gpu_smoke.py'), '--node', name, '--device', str(device), '--rank', str(rank)],
                cwd=ROOT, env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(device)), stdout=stream, stderr=subprocess.STDOUT)
        launched_workers = False
        while True:
            finished = all((RUN / 'smoke' / name / f'device{d:02d}.json').exists() for d in node['devices'])
            if finished and not (directory / 'GPU_SMOKE_PASS.json').exists():
                atomic(directory / 'GPU_SMOKE_PASS.json', dict(status='PASS', time=stamp(),
                       devices=node['devices'], ranks=[node['rank_base']+d for d in node['devices']]))
            cpu_script = ROOT / 'code/r2_cpu.py'
            ready = ROOT / 'config/CPU_WORKERS_READY.json'
            if finished and not launched_workers and cpu_script.exists() and ready.exists():
                assert sha(cpu_script) == read(ready)['source_sha256']
                for index in range(node['cpu_workers_after_smoke']):
                    ident = name + f'_cpu{index:02d}'
                    stream = (directory / (ident + '.log')).open('a'); streams.append(stream)
                    processes[ident] = subprocess.Popen([sys.executable, '-u', '-B', str(cpu_script),
                        '--worker', ident, '--threads', str(node['cpu_threads'])], cwd=ROOT,
                        stdout=stream, stderr=subprocess.STDOUT)
                launched_workers = True
            gpu_ready = ROOT / 'config/GPU_WORKERS_READY.json'
            if finished and gpu_ready.exists():
                config = read(gpu_ready)
                for device in node['devices']:
                    key = f'gpu_{config["version"]}_{device}'
                    if key in processes: continue
                    script = ROOT / config['script']; assert sha(script) == config['source_sha256']
                    stream = (directory / (key + '.log')).open('a'); streams.append(stream)
                    processes[key] = subprocess.Popen([sys.executable, '-u', '-B', str(script), '--node', name,
                        '--device', str(device), '--rank', str(node['rank_base'] + device)], cwd=ROOT,
                        env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(device)), stdout=stream, stderr=subprocess.STDOUT)
            states = {key: {'pid': process.pid, 'returncode': process.poll()} for key, process in processes.items()}
            failures = {k:v for k,v in states.items() if v['returncode'] not in [None, 0]}
            atomic(directory / 'LIVE.json', dict(status='CHILD_FAILURE_RETAINED' if failures else 'RUNNING',
                   time=stamp(), node=name, job=node['job'], pid=os.getpid(), gpu_smoke_complete=finished,
                   cpu_workers_started=launched_workers, children=states, failures=failures,
                   cpu_busy=psutil.cpu_percent(), memory_available=psutil.virtual_memory().available,
                   retained=True))
            time.sleep(15)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--node', required=True); args = p.parse_args()
    try: main(args.node)
    except BaseException as error:
        atomic(RUN / 'failures' / ('node_' + args.node + '.json'),
               dict(status='FAILED', time=stamp(), error=repr(error), traceback=traceback.format_exc()))
        raise
