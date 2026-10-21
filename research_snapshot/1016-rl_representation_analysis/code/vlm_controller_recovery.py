"""Replace only a failed CPU observer; keep its live children and all GPU work."""
from common import *
import psutil,signal,subprocess,traceback,shutil
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

DEST = VOUT/'controller_recovery_v1'


def identity(pid, script):
    p = psutil.Process(pid)
    assert p.cwd() == str(ROOT) and pid != 1
    assert any(x == 'code/'+script or x == str(ROOT/'code'/script) for x in p.cmdline()), (pid, script)
    assert p.status() != psutil.STATUS_ZOMBIE
    return p, dict(pid=pid, created=p.create_time(), command=p.cmdline())


def main():
    setup('vlm_repair/controller_recovery')
    for path, h in read(VOUT/'CONTROLLER_RECOVERY_EXECUTION.json')['code_sha256'].items():
        assert sha(ROOT/path) == h, path
    assert not (DEST/'RECOVERED.json').exists(), 'Recovery already committed; do not duplicate.'
    failure = VOUT/'failures/controller_global.json'
    value = read(failure)
    assert value['controller'] == 'global' and value['pid'] == 40816 and value['returncode'] == 1
    log = ROOT/value['original_log']
    text = log.read_text()
    assert "FileNotFoundError: [Errno 2] No such file or directory:" in text
    assert str(VOUT/'scan/claims/') in text and "VOUT.glob('**/failures/*.json')" in text
    assert not (VOUT/'global_funnel/PARENT_LOCK.json').exists()
    parent_id = int((VOUT/'container_launches/controllers_v2_node1.pid').read_text())
    parent, parent_proof = identity(parent_id, 'vlm_controller_host_v2.py')
    old = read(VOUT/'controllers/node1/LAUNCHED.json')
    children = {}
    for name, script in [('residual', 'vlm_residual_candidates.py'), ('schedule', 'vlm_scan_schedule.py')]:
        process, proof = identity(old['controllers'][name], script)
        assert process.ppid() == parent_id
        children[name] = proof
    atomic(DEST/'BEFORE.json', dict(time=stamp(), parent=parent_proof, retained_children=children,
                                  original_failure=value, original_log_sha256=sha(log), no_scientific_result_modified=True))
    shutil.copyfile(log, DEST/'original_global_traceback.log')
    # This auxiliary CPU observer is distinct from DLC main and GPU queues.
    parent.send_signal(signal.SIGTERM)
    parent.wait(timeout=10)
    shutil.move(str(failure), str(DEST/'original_controller_global_failure.json'))
    for name, proof in children.items():
        p = psutil.Process(proof['pid'])
        assert p.create_time() == proof['created'] and p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    stream = (DEST/'global_v6.log').open('a')
    child = subprocess.Popen([sys.executable, '-u', '-B', str(ROOT/'code/vlm_global_funnel_v6.py')], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    atomic(DEST/'RECOVERED.json', dict(status='PASS', time=stamp(), global_pid=child.pid,
            retained_children=children, retired_cpu_observer=parent_id, archived_original_exception=True,
            replacement='Frozen V5 with fixed-directory error observation only', gpu_and_dlc_main_processes_untouched=True))
    while True:
        result = child.poll()
        if result is not None and result != 0:
            raise RuntimeError('Recovered global controller failed; inspect original recovery/global_v6.log')
        for name, proof in children.items():
            try:
                p = psutil.Process(proof['pid'])
                alive = p.create_time() == proof['created'] and p.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                alive = False
            if not alive:
                if name == 'residual':
                    status = read(VOUT/'residual_development/STATUS.json')
                    assert status['blocks_replayed'] == status['targets'], name
                else:
                    assert len(list((VOUT/'scan/receipts').glob('*.json'))) == 2272, name
        atomic(DEST/'STATUS.json', dict(time=stamp(), global_pid=child.pid, global_returncode=result,
                                       original_residual_and_scheduler_preserved=True))
        time.sleep(30)


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        atomic(VOUT/'failures/controller_recovery.json', dict(status='FAILED', time=stamp(), error=repr(exc), traceback=traceback.format_exc()))
        raise
