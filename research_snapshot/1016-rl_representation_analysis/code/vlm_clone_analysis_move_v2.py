"""Retry idle-waiter migration with its gate and stable CPU-time evidence."""
from common import *
import argparse,socket,psutil
import vlm_clone_analysis_move as previous
from vlm_elastic_registry import DEST
from repair_queue_v2 import atomic_unique as atomic

def retire(a):
    old=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']=='legacy_0')
    assert socket.gethostname().startswith(old['job'])
    assert not previous.DONE.exists() and not (DEST.parent/'POSTCOMPUTE_REVIEW_READY.json').exists()
    ready=read(DEST/'DYNAMIC_ACCEPTANCE_READY.json');state=read(ROOT/ready['folder']/'STATUS.json')
    assert state['dynamic_acceptance_ready'] and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(state['time'])).total_seconds()<120
    found=[]
    for p in psutil.process_iter(['cwd','cmdline']):
        try:
            scripts=[Path(x).name for x in p.info['cmdline'] or [] if str(x).endswith('.py')]
            if p.info['cwd']==str(ROOT) and 'vlm_analysis_finalize.py' in scripts and 'vlm_elastic_entry.py' not in scripts:found.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert len(found)==1,[p.pid for p in found];p=found[0];assert not p.children(recursive=True)
    before=p.cpu_times();time.sleep(1);after=p.cpu_times()
    assert after.user+after.system-before.user-before.system<=.02
    assert not (DEST.parent/'POSTCOMPUTE_REVIEW_READY.json').exists() and not p.children(recursive=True)
    record=dict(pid=p.pid,created=p.create_time(),cmdline=p.cmdline(),cwd=p.cwd())
    assert not (previous.MOVE/'RETIRED.json').exists()
    atomic(previous.MOVE/'INTENT.json',dict(status='VERIFIED_IDLE_ANALYSIS_ONLY',time=stamp(),record=record,job=old['job'],
        gate_absent=True,no_children=True,one_second_cpu_change=after.user+after.system-before.user-before.system))
    p.terminate();stopped=False;end=time.monotonic()+25
    while time.monotonic()<end:
        try:stopped=p.status()==psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:stopped=True
        if stopped:break
        time.sleep(.2)
    assert stopped
    atomic(previous.MOVE/'RETIRED.json',dict(status='PASS',time=stamp(),record=record,job=old['job'],
        verified_no_active_child=True,no_compute_or_DLC_master_stopped=True,script_sha256=sha(previous.SCRIPT),
        gate_and_CPU_time_checked=True,checker_sha256=sha(Path(__file__))))
    print('IDLE_ANALYSIS_WAITER_RETIRED',record['pid'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['retire','service']);p.add_argument('--id');a=p.parse_args();setup('vlm_repair/clone_analysis_move_v2')
    for path,h in read(DEST/'CLONE_ANALYSIS_MOVE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    retire(a) if a.mode=='retire' else previous.service(a)
