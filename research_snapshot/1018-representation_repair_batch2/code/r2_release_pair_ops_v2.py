"""User-authorized retirement of self_0/self_1; other nodes stay active.

Independent operational helper. Frozen scientific handlers and queues are not
modified. Exact process identities are checked before every signal.
"""
from r2_common import *
import argparse
import subprocess
import psutil


def identity(p):
    return dict(pid=p.pid, created=p.create_time(), cmdline=p.cmdline(), uid=p.uids().real)


def exact(r):
    p = psutil.Process(r['pid'])
    assert p.create_time() == r['created']
    assert p.uids().real == r['uid'] == os.getuid()
    assert p.cmdline() == r['cmdline']
    return p


def alive(r):
    try:
        p = psutil.Process(r['pid'])
        if p.create_time() != r['created'] or p.status() == psutil.STATUS_ZOMBIE:
            return False
        exact(r)
        return True
    except psutil.NoSuchProcess:
        return False


def source_of(command):
    sources = [Path(x) for x in command if x.startswith(str(ROOT / 'code') + '/') and x.endswith('.py')]
    assert len(sources) == 1, command
    return sources[0]


def current_boundary(item):
    state = read(ROOT / item['status_file'])
    if state['status'] == 'QUEUE_WAIT':
        return True, state, None
    if state['status'] != 'COMPUTING':
        return False, state, None
    if item['kind'] == 'cpu':
        paths = [RUN / k / (state['task'] + '.json') for k in ['receipts_cpu', 'failures_cpu']]
    else:
        paths = [ROOT / state['stage'] / k / (state['task'] + '.json') for k in ['receipts', 'failures']]
    for path in paths:
        if retry(path.exists):
            return True, state, str(path.relative_to(ROOT))
    return False, state, None


def drain(a, folder, intent):
    assert a.node in intent['targets']
    job = intent['targets'][a.node]
    assert socket.gethostname().startswith(job + '-')
    dest = folder / a.node
    workers = []
    parents = []
    for p in psutil.process_iter(['cmdline']):
        try:
            command = p.info['cmdline'] or []
            paths = {Path(x).name for x in command if x.startswith(str(ROOT / 'code') + '/')}
            if '--node' in command and command[command.index('--node') + 1] == a.node:
                if 'r2_gpu.py' in paths:
                    status = RUN / 'dispatch_workers' / (socket.gethostname() + '_' + str(p.pid) + '.json')
                    kind = 'gpu'
                elif 'r2_gpu_background.py' in paths:
                    device = int(command[command.index('--device') + 1])
                    tag = command[command.index('--tag') + 1]
                    status = RUN / 'background_gpu' / a.node / f'device{device:02d}' / tag / 'LIVE.json'
                    kind = 'background'
                elif paths & {'r2_node.py', 'r2_background_supervisor.py'}:
                    parents.append(identity(p))
                    continue
                else:
                    continue
            elif paths & {'r2_cpu.py', 'r2_cpu_extra.py', 'r2_cpu_recovery_v1.py', 'r2_cpu_recovery_v2.py'}:
                worker = command[command.index('--worker') + 1]
                if not worker.startswith(a.node + '_'):
                    continue
                status = RUN / 'workers_cpu' / (worker + '.json')
                kind = 'cpu'
            else:
                continue
            assert p.pid > 10 and p.uids().real == os.getuid() and retry(status.exists)
            workers.append(dict(process=identity(p), kind=kind,
                                status_file=str(status.relative_to(ROOT))))
        except psutil.NoSuchProcess:
            continue
    counts = {k: sum(w['kind'] == k for w in workers) for k in ['cpu', 'gpu', 'background']}
    assert counts['gpu'] == 16 and counts['cpu'] >= 24 and len(parents) == 2, counts
    if (dest / 'DRAIN_START.json').exists():
        prior = read(dest / 'DRAIN_START.json')
        workers, parents = prior['workers'], prior['parents']
        counts = prior['counts']
    else:
        atomic(dest / 'DRAIN_START.json', dict(time=stamp(), job=job, node=a.node, workers=workers, parents=parents, counts=counts, no_global_queue_change=True))
    atomic(dest / 'DRAIN_ATTEMPT_V2.json', dict(time=stamp(), reused_original_identities=True, workers=len(workers)))
    for r in parents:
        exact(r).suspend()
    pending = {w['process']['pid']: w for w in workers}
    paused = []
    began = time.monotonic()
    while pending:
        for pid, item in list(pending.items()):
            assert alive(item['process']), ('Worker exited before accepted boundary', item)
            done, state, terminal = current_boundary(item)
            if not done:
                continue
            p = exact(item['process'])
            p.suspend()
            stopped_deadline = time.monotonic() + 2
            while time.monotonic() < stopped_deadline and p.status() != psutil.STATUS_STOPPED:
                time.sleep(.01)
            assert p.status() == psutil.STATUS_STOPPED
            done, state, terminal = current_boundary(item)
            if not done:
                p.resume()
                continue
            paused.append(dict(**item, paused_at=stamp(), last_status=state,
                terminal_record=terminal, prehandler_claim_possible_and_preserved=True))
            pending.pop(pid)
        atomic(dest / 'DRAIN_LIVE.json', dict(time=stamp(), status='DRAINING_RECEIPT_BOUNDARIES',
            paused=len(paused), remaining=len(pending), remaining_items=list(pending.values()),
            seconds=time.monotonic() - began, no_task_forced_termination=True))
        if pending:
            time.sleep(2)
    atomic(dest / 'QUIESCENT.json', dict(time=stamp(), status='ALL_SCIENTIFIC_WORKERS_AT_DURABLE_BOUNDARIES',
        node=a.node, job=job, counts=counts, workers=paused, suspended_parents=parents,
        no_claims_removed=True, no_scientific_outputs_overwritten=True))
    print(json.dumps(dict(status='QUIESCENT', node=a.node, counts=counts)), flush=True)


def prepare_control(a, folder, intent):
    assert socket.gethostname().startswith(intent['targets']['self_0'] + '-')
    live = read(RUN / 'control_plane/LIVE.json')
    assert live['node'] == 'self_0' and live['job'] == intent['targets']['self_0']
    parent = psutil.Process(live['pid'])
    assert str(ROOT / 'code/r2_control_handoff_v1.py') in parent.cmdline()
    assert parent.uids().real == os.getuid()
    active = []
    excluded = []
    for name, state in live['children'].items():
        if state['returncode'] is not None:
            excluded.append(name)
            continue
        try:
            p = psutil.Process(state['pid'])
            if p.status() == psutil.STATUS_ZOMBIE:
                excluded.append(name)
                continue
            assert p.ppid() == parent.pid and not p.children(recursive=True)
            r = identity(p)
            source = source_of(r['cmdline'])
            assert r['uid'] == os.getuid()
            active.append(dict(name=name, process=r, command=r['cmdline'], cwd=p.cwd(),
                               source=str(source.relative_to(ROOT)), source_sha256=sha(source)))
        except psutil.NoSuchProcess:
            excluded.append(name)
    assert len(active) >= 60
    atomic(folder / 'control/PREPARED.json', dict(time=stamp(), old_parent=identity(parent),
        active=active, excluded_ids=excluded, destination=intent['control_destination'],
        metadata_only=True, no_signal_sent=True))
    print(json.dumps(dict(status='CONTROL_PREPARED', active=len(active), excluded=len(excluded))), flush=True)


def retire_control(a, folder, intent):
    assert socket.gethostname().startswith(intent['targets']['self_0'] + '-')
    manifest = read(folder / 'control/PREPARED.json')
    ready = read(folder / 'control/STANDBY_READY.json')
    assert ready['job'] == intent['control_destination']['job']
    parent = exact(manifest['old_parent'])
    parent.suspend()
    active = []
    completed_after_prepare = []
    for child in manifest['active']:
        if not alive(child['process']):
            completed_after_prepare.append(child['name'])
            continue
        p = exact(child['process'])
        assert p.ppid() == parent.pid and not p.children(recursive=True)
        assert sha(ROOT / child['source']) == child['source_sha256']
        active.append(child)
    manifest.update(active=active, excluded_ids=manifest['excluded_ids'] + completed_after_prepare)
    atomic(folder / 'control/RETIRE_INTENT.json', dict(time=stamp(), manifest=manifest))
    for child in active:
        if alive(child['process']):
            exact(child['process']).terminate()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline and any(alive(c['process']) for c in active):
        time.sleep(.2)
    assert not any(alive(c['process']) for c in active), 'Metadata children did not terminate'
    exact(manifest['old_parent']).terminate()
    exact(manifest['old_parent']).resume()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and alive(manifest['old_parent']):
        time.sleep(.2)
    assert not alive(manifest['old_parent'])
    atomic(folder / 'control/RETIRED.json', dict(time=stamp(), manifest=manifest,
        status='OLD_METADATA_CONTROLLERS_TERMINAL', scientific_workers_untouched=True))
    print(json.dumps(dict(status='CONTROL_RETIRED', active=len(active))), flush=True)


def control(a, folder, intent):
    dest = intent['control_destination']
    assert socket.gethostname().startswith(dest['job'] + '-')
    live_node = read(RUN / 'nodes' / dest['node'] / 'LIVE.json')
    assert live_node['job'] == dest['job'] and (RUN / 'nodes' / dest['node'] / 'GPU_SMOKE_PASS.json').exists()
    setup('control_pair_release/' + dest['node'])
    atomic(folder / 'control/STANDBY_READY.json', dict(time=stamp(), **dest,
        process=identity(psutil.Process()), source_sha256=sha(Path(__file__))))
    while not (folder / 'control/RETIRED.json').exists():
        time.sleep(1)
    manifest = read(folder / 'control/RETIRED.json')['manifest']
    guard = (RUN / 'control_plane/LEADER.lock').open('a+')
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    children = {c['name']: c for c in manifest['active']}
    excluded = set(manifest['excluded_ids'])
    processes = {}
    streams = []
    atomic(folder / 'control/ACTIVE.json', dict(time=stamp(), **dest,
        process=identity(psutil.Process()), single_leader_lock_acquired=True,
        old_metadata_terminal_before_new_start=True, active_ids=list(children), excluded_ids=sorted(excluded)))
    while True:
        for source in read(ROOT / 'config/CONTROL_SCRIPTS_V1.json')['scripts']:
            name = source['id']
            if name in excluded or name in processes:
                continue
            if name not in children:
                children[name] = dict(name=name, command=[sys.executable, '-u', '-B',
                    str(ROOT / source['script']), *source.get('arguments', [])], cwd=str(ROOT),
                    source=source['script'], source_sha256=source['source_sha256'])
            child = children[name]
            assert sha(ROOT / child['source']) == child['source_sha256']
            log = folder / 'control/logs' / (name + '.log')
            log.parent.mkdir(parents=True, exist_ok=True)
            stream = log.open('a')
            streams.append(stream)
            processes[name] = subprocess.Popen(child['command'], cwd=child['cwd'],
                stdout=stream, stderr=subprocess.STDOUT)
        states = {n: dict(pid=p.pid, returncode=p.poll()) for n, p in processes.items()}
        failures = {n: v for n, v in states.items() if v['returncode'] not in [None, 0]}
        for name, value in failures.items():
            path = folder / 'control/failures' / (name + '.json')
            if not path.exists():
                atomic(path, dict(time=stamp(), node=dest['node'], job=dest['job'],
                    controller=name, process=value, no_automatic_restart=True))
        atomic(RUN / 'control_plane/LIVE.json', dict(time=stamp(), node=dest['node'],
            job=dest['job'], pid=os.getpid(), children=states, failures=failures, retained=True,
            migration_proof=str((folder / 'control/ACTIVE.json').relative_to(ROOT))))
        atomic(folder / 'control/HEARTBEAT.json', dict(time=stamp(), processes=len(processes), failures=failures))
        time.sleep(15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['drain', 'prepare_control', 'retire_control', 'control'])
    parser.add_argument('--folder', required=True)
    parser.add_argument('--node')
    args = parser.parse_args()
    folder = (ROOT / args.folder).resolve()
    assert folder.is_relative_to(ROOT)
    intent = read(folder / 'INTENT.json')
    try:
        globals()[args.action](args, folder, intent)
    except BaseException as error:
        import traceback
        atomic(folder / ('FAILED_' + args.action + '_' + str(args.node) + '.json'),
            dict(time=stamp(), error=repr(error), traceback=traceback.format_exc()))
        raise
