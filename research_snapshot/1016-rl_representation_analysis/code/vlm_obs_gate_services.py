"""Supervise fifth-batch CPU preparation and compatible sparse inference producer."""
from common import *
import psutil,subprocess,traceback,fcntl
from vlm_core import VOUT
from vlm_obs_qda_gate import OUT
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/obs_gate_services');folder=OUT/'services';folder.mkdir(exist_ok=True)
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    for p,h in read(VOUT/'OBS_QDA_GATE_SERVICES_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    with (folder/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cores=[]
        for p in psutil.process_iter(['pid','cwd','cmdline']):
            if p.info['cwd']==str(ROOT) and any(x in [str(ROOT/'code/vlm_obs_qda_gate.py'),'code/vlm_obs_qda_gate.py'] for x in (p.info['cmdline'] or [])):cores.append(p)
        finished=(OUT/'FINAL_LOCK.json').exists() or (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists()
        assert len(cores)==1 or (not cores and finished)
        core=cores[0] if cores else None;created=core.create_time() if core else None
        stream=(folder/'test_controller.log').open('a')
        child=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_obs_gate_test.py')],cwd=ROOT,
            stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10))
        atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),cpu=os.cpu_count(),
            available_memory=psutil.virtual_memory().available,core_pid=core.pid if core else None,
            core_created=created,test_controller_pid=child.pid,no_GPU_worker_created=True))
        while True:
            finished=(OUT/'FINAL_LOCK.json').exists() or (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists()
            if not finished:
                assert core is not None and core.is_running() and core.status()!=psutil.STATUS_ZOMBIE
                assert core.create_time()==created
            rc=child.poll();assert rc in [None,0],('Sparse test controller failed',rc)
            if rc==0:assert (OUT/'INFERENCE_COMPLETE.json').exists() or (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists()
            atomic(folder/'STATUS.json',dict(time=stamp(),core_selection_complete=finished,
                test_controller_pid=child.pid,test_controller_returncode=rc,existing_queues_retained=True))
            time.sleep(30)


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(OUT/'failures/services.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
