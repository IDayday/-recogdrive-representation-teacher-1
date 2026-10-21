"""Recover a CPU waiter after an optional wave resource check was misclassified.

Never signals the retained DLC master, GPU workers or existing CPU scans. Keeps
the master's historical child-failure record visible with an explicit resolution.
"""
from common import *
import argparse, subprocess, traceback, shutil
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic


def main(a):
    setup('vlm_repair/cold_global_recovery')
    resume = (ROOT/a.resume).resolve()
    assert resume.is_relative_to(VOUT/'resume')
    dest = resume/'global_recovery_v1'
    dest.mkdir(exist_ok=False)
    import psutil
    masters=[]
    for process in psutil.process_iter(['pid','cmdline','cwd']):
        cmd=process.info['cmdline'] or []
        if process.info['cwd']==str(ROOT) and any(x.endswith('/vlm_resume_node_v3.py') or x=='code/vlm_resume_node_v3.py' for x in cmd):
            masters.append(process)
    assert len(masters)==1
    master=masters[0]
    expected = ['scan_wave_node_0_1_None.json', 'global_funnel_v6.json']
    saved = []
    for name in expected:
        p = VOUT/'failures'/name
        value = read(p)
        if name.startswith('scan_wave'):
            assert "Review measured load before adding workers" in value['error'] and '78.8' in value['error']
            assert not (resume/'cpu_wave/node0_wave1').exists()
        else:
            assert 'scan_wave_node_0_1_None.json' in value['error']
        saved.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),value=value))
    marker = resume/'node1/failures/global.json'
    historical = read(marker)
    assert historical['pid'] == 15 and historical['returncode'] == 1 and historical['status'] == 'FAILED'
    old_log = ROOT/historical['original_log']
    assert 'scan_wave_node_0_1_None.json' in old_log.read_text()
    atomic(dest/'CAUSE.json', dict(status='AUXILIARY_RESOURCE_DEFERRAL_MISCLASSIFIED', time=stamp(),
            saved=saved, historical_master_record=historical, old_log_sha256=sha(old_log),
            retained_master_pid=master.pid, retained_master_created=master.create_time(),
            no_second_wave_workers_started=True, no_scientific_results_invalidated=True))
    shutil.copyfile(old_log, dest/'original_global.log')
    for name in expected:
        shutil.move(str(VOUT/'failures'/name), str(dest/name))
    out = (dest/'global_restarted.log').open('a')
    child = subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_global_funnel_v6.py')],
            cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
    resolution = dict(marker=str(marker.relative_to(ROOT)),
            signature={k:historical[k] for k in ['pid','returncode','status','original_log']},
            old_log_sha256=sha(old_log), status_path=str((dest/'STATUS.json').relative_to(ROOT)),
            replacement_pid=child.pid, replacement_code_sha256=sha(ROOT/'code/vlm_global_funnel_v6.py'),
            cause_path=str((dest/'CAUSE.json').relative_to(ROOT)))
    atomic(dest/'RESOLUTION.json', dict(status='EXPLICIT_RESOLUTION_NOT_MARKER_DELETION',time=stamp(),**resolution))
    atomic(resume/'RESOLVED_FAILURES.json', dict(time=stamp(), records=[resolution]))
    while True:
        rc = child.poll()
        if rc is not None:
            assert rc == 0 and (VOUT/'global_funnel/FINAL_CANDIDATE_LOCK.json').exists(), rc
        atomic(dest/'STATUS.json', dict(status='RUNNING' if rc is None else 'COMPLETE', time=stamp(),
                pid=child.pid, returncode=rc, dlc_master_and_gpu_processes_untouched=True))
        time.sleep(15)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--resume',required=True);a=p.parse_args()
    try:
        main(a)
    except BaseException as exc:
        atomic(VOUT/'failures/cold_global_recovery.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()))
        raise
