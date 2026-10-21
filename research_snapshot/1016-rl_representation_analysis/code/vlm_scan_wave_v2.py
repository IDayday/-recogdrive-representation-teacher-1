"""Additional low-priority CPU waves using the unchanged full-grid scanner.

Starts only in a newly verified continuation, after breadth-first canonical
coverage and release of the original deferred tasks. No extra model workers.
"""
from common import *
import argparse, subprocess, traceback
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic


def assignments(node, wave):
    low_start, low_count = [(0, 32), (32, 16), (48, 16)][wave]
    high_start, high_count = [(0, 16), (16, 8), (24, 8)][wave]
    return ([(512+node*1024+low_start+i, 'low') for i in range(low_count)]
            + [(768+node*1024+high_start+i, 'high') for i in range(high_count)])


def worker(a):
    import vlm_scan_queue as module
    dimensions = {b['name']: b['shape'][1] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']}
    original = module.claim

    def claim(tasks, rank, workers):
        low = [t for t in tasks if dimensions[t['block']] <= 1536]
        if a.role == 'low':
            return original(low, rank, workers)
        high = [t for t in tasks if dimensions[t['block']] > 1536]
        chosen = original(high, rank, workers)
        return chosen if chosen is not None else original(low, rank, workers)

    module.claim = claim
    module.worker(a)


def node(a):
    setup(f'vlm_repair/scan_wave/{a.node}/{a.wave}')
    import psutil
    launch = (ROOT/a.launch).resolve()
    assert launch.is_relative_to(VOUT/'resume')
    assert read(VOUT/'FULL_GRID_ALL_RELEASED.json')['canonical_completed'] == 62
    # The task-scoped container command has independently checked its new JobId.
    assert os.cpu_count() >= 160 and len(os.sched_getaffinity(0)) >= 160
    memory = psutil.virtual_memory().available
    assert memory > 256*1024**3
    p = read(VOUT/'SCAN_WAVE_EXECUTION_v2.json')
    for path, h in p['code_sha256'].items():
        assert sha(ROOT/path) == h, path
    busy = psutil.cpu_percent(interval=3)
    if busy >= (85 if a.wave == 0 else 78):
        launch.mkdir(parents=True, exist_ok=False)
        atomic(launch/'DEFERRED.json', dict(status='DEFERRED_NO_WORKERS_STARTED', time=stamp(),
                node=a.node, wave=a.wave, cpu_busy_percent=busy,
                reason='Insufficient measured headroom; retain current workers and retry with a new launch directory.'))
        print('CPU_WAVE_DEFERRED_NO_EXPERIMENTAL_FAILURE', a.node, a.wave, busy, flush=True)
        return
    launch.mkdir(parents=True, exist_ok=False)
    ranks = assignments(a.node, a.wave)
    assert all(rank//1024 == a.node for rank, role in ranks)
    atomic(launch/'PREFLIGHT.json', dict(status='PASS', time=stamp(), node=a.node, wave=a.wave,
            ranks=ranks, threads=2, nice=10, available_memory=memory, cpu_busy_percent=busy,
            frozen_scanner_sha256=sha(ROOT/'code/vlm_scan.py')))
    children = []
    streams = []
    for rank, role in ranks:
        stream = (launch/f'rank{rank:04d}.log').open('a')
        streams.append(stream)
        cmd = [sys.executable, '-u', '-B', str(Path(__file__).resolve()), 'worker',
               '--rank', str(rank), '--workers', '1024', '--threads', '2', '--role', role]
        children.append(subprocess.Popen(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                        preexec_fn=lambda: os.nice(10)))
    checked = False
    while True:
        bad = [(r, p.poll()) for (r, role), p in zip(ranks, children) if p.poll() is not None]
        assert not bad, bad
        if not checked and all((VOUT/f'scan/smoke/rank{r:03d}.json').exists() for r, role in ranks):
            atomic(launch/'SMOKE_PASS.json', dict(status='PASS', time=stamp(), ranks=ranks,
                    all_numeric_references_actually_checked=True))
            checked = True
        atomic(launch/'STATUS.json', dict(time=stamp(), node=a.node, wave=a.wave,
                workers={r: p.pid for (r, role), p in zip(ranks, children)}, main_and_gpu_unchanged=True))
        time.sleep(30)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['node', 'worker'])
    p.add_argument('--node', type=int, choices=[0, 1])
    p.add_argument('--wave', type=int, choices=[0, 1, 2])
    p.add_argument('--launch')
    p.add_argument('--rank', type=int)
    p.add_argument('--workers', type=int, default=1024)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--role', choices=['low', 'high'])
    a = p.parse_args()
    try:
        globals()[a.mode](a)
    except BaseException as exc:
        atomic(VOUT/'failures'/f'scan_wave_{a.mode}_{a.node}_{a.wave}_{a.rank}.json',
               dict(status='FAILED', time=stamp(), error=repr(exc), traceback=traceback.format_exc()))
        raise
