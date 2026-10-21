"""Continue only producers explicitly paused in a confirmed retired legacy job."""
from common import *
import argparse,fcntl,subprocess,traceback,runpy
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

MARKERS={
 'vlm_final_driver.py':DEST.parent/'final/PRIMARY_INFERENCE_COMPLETE.json',
 'vlm_semantic_repair_v3.py':ROOT/'vlm_semantic_v2/repair/INFERENCE_COMPLETE.json',
 'vlm_ungated_final.py':DEST.parent/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json',
 'vlm_late_repair.py':DEST.parent/'late_token_coverage/INFERENCE_COMPLETE.json',
 'vlm_qneighbor_repair_v2.py':DEST.parent/'qda_neighbor_repair/INFERENCE_COMPLETE.json',
 'vlm_obs_gate_test.py':DEST.parent/'observation_qda_gate/INFERENCE_COMPLETE.json',
 'vlm_obs_qda_gate.py':DEST.parent/'observation_qda_gate/FINAL_LOCK.json'}
WRAPPED={'vlm_final_driver.py','vlm_semantic_repair_v3.py','vlm_late_repair.py','vlm_qneighbor_repair_v2.py','vlm_obs_gate_test.py'}

def finished(script):
    marker=MARKERS[script]
    return marker.exists() or (marker.parent/'NO_COMPETITIVE_CANDIDATES.json').exists()

def execute(a):
    assert a.script in MARKERS
    setup('vlm_repair/elastic_producer/'+Path(a.script).stem)
    lockpath=DEST/'producer_locks'/(a.script+'.lock');lockpath.parent.mkdir(exist_ok=True)
    with lockpath.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if finished(a.script):return
        if a.script in WRAPPED:
            import vlm_resume_frozen_controller_v2 as module
            class Args:pass
            args=Args();args.script=Path(a.script).stem;module.main(args)
        else:
            sys.argv=[str(ROOT/'code'/a.script)];runpy.run_path(sys.argv[0],run_name='__main__')

def service(a):
    c=configuration(a.id);assert read(ROOT/c['folder']/'PREFLIGHT.json')['status']=='PASS'
    source=(ROOT/a.retirement).resolve();assert source.is_relative_to(DEST/'rolling')
    assert read(source/'TERMINAL_CONFIRMED.json')['status']=='PASS'
    proof=read(source/'QUIESCED.json');names=set()
    for r in proof['paused_processes']:
        if r['kind']=='producer':
            script=next(Path(z).name for z in r['cmdline'] if str(z).endswith('.py'))
            assert script in MARKERS;names.add(script)
    folder=(ROOT/a.folder).resolve();assert folder.is_relative_to(DEST);folder.mkdir(parents=True,exist_ok=False)
    children={};streams=[]
    for name in sorted(names):
        if finished(name):continue
        stream=(folder/(name+'.log')).open('a');streams.append(stream)
        children[name]=subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'execute','--script',name],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),host=a.id,source_retirement_sha256=sha(source/'TERMINAL_CONFIRMED.json'),
        processes={name:p.pid for name,p in children.items()},original_numerical_sources_unchanged=True))
    while True:
        state={}
        for name,p in children.items():
            rc=p.poll();assert rc in [None,0],(name,rc)
            if rc==0:assert finished(name),name
            state[name]=dict(pid=p.pid,returncode=rc,status='RUNNING' if rc is None else 'COMPLETE')
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host=a.id,processes=state,main_and_shared_queues_retained=True))
        time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['execute','service']);p.add_argument('--script');p.add_argument('--id');p.add_argument('--retirement');p.add_argument('--folder');a=p.parse_args();setup('vlm_repair/elastic_producers')
    try:globals()[a.mode](a)
    except BaseException as error:
        atomic(DEST/'failures'/f'producer_{a.mode}_{a.script}_{a.id}.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
