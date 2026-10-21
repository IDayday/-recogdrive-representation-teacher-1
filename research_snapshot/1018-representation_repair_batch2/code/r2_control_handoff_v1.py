"""Move only verified metadata controllers; all scientific workers continue."""
from r2_common import *
import argparse
import subprocess
import psutil

DEST = ROOT/'resources/handoffs/peer_b1_20261019/control_migration'


def identity(p):
    return dict(pid=p.pid, created=p.create_time(), cmdline=p.cmdline(), uid=p.uids().real)


def same(record):
    p = psutil.Process(record['pid'])
    assert p.create_time() == record['created'] and p.cmdline() == record['cmdline']
    assert p.uids().real == record['uid'] == os.getuid()
    return p


def alive(record):
    try:
        p = psutil.Process(record['pid'])
        assert p.create_time() == record['created']
        if p.status() == psutil.STATUS_ZOMBIE: return False
        p = same(record)
        return p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess: return False


def retire():
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert read(DEST/'STANDBY_READY.json')['node'] == 'self_0'
    assert not (DEST/'RETIRED.json').exists()
    live = read(RUN/'control_plane/LIVE.json')
    assert live['node'] == 'peer_b1'
    parent = psutil.Process(live['pid']); parent_record = identity(parent)
    assert str(ROOT/'code/r2_control_supervisor.py') in parent.cmdline()
    assert parent.pid > 10 and parent.uids().real == os.getuid()
    config = read(ROOT/'config/CONTROL_SCRIPTS_V1.json'); by_id = {c['id']:c for c in config['scripts']}
    active = []; excluded = []
    for name, state in live['children'].items():
        if state['returncode'] is not None:
            excluded.append(name); continue
        try: p = psutil.Process(state['pid'])
        except psutil.NoSuchProcess:
            excluded.append(name); continue
        if p.status() == psutil.STATUS_ZOMBIE:
            excluded.append(name); continue
        child = by_id[name]
        assert p.ppid() == parent.pid and not p.children(recursive=True)
        assert str(ROOT/child['script']) in p.cmdline()
        assert sha(ROOT/child['script']) == child['source_sha256']
        active.append(dict(name=name, process=identity(p), source=child))
    assert len(active) > 60
    override = read(DEST.parent/'CAPACITY_PRODUCER_RESTART_GUARD.json')
    manifest = dict(time=stamp(), old_parent=parent_record, active=active, excluded_ids=excluded,
        source_overrides={'full_capacity_matched_expert_fold_fit_replication_v2_canonical':dict(
            script=override['new_source'], source_sha256=override['new_sha256'])},
        proof='Metadataonly; exactparentchild/UID/creationtime/cmdline/sourceSHA; no children. Scientific workers untouched.')
    atomic(DEST/'RETIRE_INTENT.json', manifest)
    parent.suspend(); assert same(parent_record).status() == psutil.STATUS_STOPPED
    try:
        for child in active:
            if alive(child['process']): same(child['process']).terminate()
        end = time.monotonic()+30
        while time.monotonic()<end and any(alive(c['process']) for c in active): time.sleep(.1)
        pending = [c for c in active if alive(c['process'])]
        assert not pending, [(c['name'], c['process']['pid']) for c in pending]
        parent.terminate(); parent.resume()
        end = time.monotonic()+10
        while time.monotonic()<end and alive(parent_record): time.sleep(.1)
        assert not alive(parent_record)
    except BaseException:
        if alive(parent_record): same(parent_record).resume()
        raise
    atomic(DEST/'RETIRED.json', dict(status='EXACT_METADATA_CONTROLLERS_RETIRED', time=stamp(),
        manifest=manifest, old_parent_dead=True, all_old_metadata_children_dead=True,
        no_GPU_CPU_scientific_worker_or_DLC_main_stopped=True))
    print(json.dumps(dict(status='CONTROL_METADATA_RETIRED', active=len(active), excluded=len(excluded))))


def standby():
    setup('control_plane_handoff/self_0')
    assert socket.gethostname().startswith('dlcrnshl7t4hcmoy-')
    assert (RUN/'nodes/self_0/GPU_SMOKE_PASS.json').exists()
    atomic(DEST/'STANDBY_READY.json', dict(time=stamp(), node='self_0', job='dlcrnshl7t4hcmoy',
        process=identity(psutil.Process()), source_sha256=sha(Path(__file__)), awaiting_retirement=True))
    while not (DEST/'RETIRED.json').exists(): time.sleep(1)
    retired = read(DEST/'RETIRED.json'); manifest = retired['manifest']; excluded = set(manifest['excluded_ids'])
    guard = (RUN/'control_plane/LEADER.lock').open('a+')
    fcntl.flock(guard, fcntl.LOCK_EX|fcntl.LOCK_NB)
    processes = {}; handles = []; sources = {}
    atomic(DEST/'ACTIVE.json', dict(time=stamp(), node='self_0', job='dlcrnshl7t4hcmoy',
        process=identity(psutil.Process()), single_leader_lock_acquired=True,
        old_parent_retired_before_new_children=True, excluded_completed_or_retired_ids=sorted(excluded)))
    while True:
        for child in read(ROOT/'config/CONTROL_SCRIPTS_V1.json')['scripts']:
            name = child['id']
            if name in excluded or name in processes: continue
            source = dict(child, **manifest['source_overrides'].get(name, {}))
            script = ROOT/source['script']; assert sha(script) == source['source_sha256']
            log = DEST/'logs'/(name+'.log'); log.parent.mkdir(parents=True, exist_ok=True)
            handle = log.open('a'); handles.append(handle)
            processes[name] = subprocess.Popen([sys.executable,'-u','-B',str(script),*source.get('arguments',[])],
                cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            sources[name] = source
        states = {name:dict(pid=p.pid, returncode=p.poll()) for name,p in processes.items()}
        for name, state in states.items():
            if state['returncode'] not in [None,0]:
                failure = RUN/'failures'/('control_moved_self0_'+name+'.json')
                if not failure.exists(): atomic(failure, dict(status='FAILED', time=stamp(), node='self_0',
                    controller=name, process=state, source=sources[name],
                    log=str((DEST/'logs'/(name+'.log')).relative_to(ROOT)), no_automatic_restart=True))
        atomic(RUN/'control_plane/LIVE.json', dict(time=stamp(), node='self_0', job='dlcrnshl7t4hcmoy',
            pid=os.getpid(), children=states, failures={k:v for k,v in states.items() if v['returncode'] not in [None,0]},
            migration_proof=str((DEST/'ACTIVE.json').relative_to(ROOT)), retained=True))
        time.sleep(15)


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode', choices=['standby','retire']); a=p.parse_args()
    try: globals()[a.mode]()
    except BaseException as error:
        import traceback
        atomic(DEST/('FAILED_'+a.mode+'.json'), dict(time=stamp(), error=repr(error), traceback=traceback.format_exc()))
        raise
