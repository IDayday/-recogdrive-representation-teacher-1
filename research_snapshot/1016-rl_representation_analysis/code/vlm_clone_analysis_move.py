"""Move only the idle original analysis waiter to a retained 72-hour clone."""
from common import *
import argparse,socket,psutil,subprocess,fcntl
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

MOVE=DEST/'analysis_move'
DONE=DEST.parent/'FINAL_ANALYSES_REVIEW_READY.json'
SCRIPT=ROOT/'code/vlm_analysis_finalize.py'

def retire(a):
    old=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']=='legacy_0')
    assert socket.gethostname().startswith(old['job'])
    assert not DONE.exists() and not (DEST.parent/'POSTCOMPUTE_REVIEW_READY.json').exists()
    service=read(DEST/'DYNAMIC_ACCEPTANCE_READY.json');status=read(ROOT/service['folder']/'STATUS.json')
    assert status['dynamic_acceptance_ready'] and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(status['time'])).total_seconds()<120
    found=[]
    for p in psutil.process_iter(['cwd','cmdline']):
        try:
            scripts=[Path(x).name for x in p.info['cmdline'] or [] if str(x).endswith('.py')]
            if p.info['cwd']==str(ROOT) and 'vlm_analysis_finalize.py' in scripts and 'vlm_elastic_entry.py' not in scripts:found.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert len(found)==1,[p.pid for p in found];p=found[0]
    assert not p.children(recursive=True)
    assert 'hrtimer_nanosleep' in Path(f'/proc/{p.pid}/wchan').read_text()
    record=dict(pid=p.pid,created=p.create_time(),cmdline=p.cmdline(),cwd=p.cwd())
    assert not (MOVE/'RETIRED.json').exists()
    atomic(MOVE/'INTENT.json',dict(status='VERIFIED_IDLE_ANALYSIS_ONLY',time=stamp(),record=record,job=old['job']))
    assert p.create_time()==record['created'] and p.cmdline()==record['cmdline'];p.terminate()
    end=time.monotonic()+25
    while time.monotonic()<end:
        try:stopped=p.status()==psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:stopped=True
        if stopped:break
        time.sleep(.2)
    assert stopped,'Original waiter has not terminated; no replacement launched.'
    atomic(MOVE/'RETIRED.json',dict(status='PASS',time=stamp(),record=record,job=old['job'],
        verified_no_active_child=True,no_compute_or_DLC_master_stopped=True,script_sha256=sha(SCRIPT)))
    print('IDLE_ANALYSIS_WAITER_RETIRED',record['pid'],flush=True)

def service(a):
    c=configuration(a.id);node=ROOT/c['folder'];lease=read(node/'ADOPTED_CLONE.json')
    assert socket.gethostname().startswith(lease['job']) and read(node/'ENGINEERING_PASS.json')['all_record_fields_exact']
    proof=read(MOVE/'RETIRED.json');assert proof['status']=='PASS' and proof['script_sha256']==sha(SCRIPT)
    MOVE.mkdir(exist_ok=True)
    with (MOVE/'service.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stream=(MOVE/'analysis.log').open('a')
        child=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_entry.py'),'--script',SCRIPT.name],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        atomic(MOVE/'SERVICE_READY.json',dict(status='PASS',time=stamp(),host=a.id,job=lease['job'],pid=child.pid,
            state_path=str((MOVE/'CHILD_STATUS.json').relative_to(ROOT)),script_sha256=sha(SCRIPT),source_sha256=sha(Path(__file__))))
        resolved=False;resume=ROOT/old_resume();marker=resume/'node0/failures/analysis_finalize.json'
        while True:
            rc=child.poll();assert rc in [None,0]
            if rc==0:assert DONE.exists()
            atomic(MOVE/'CHILD_STATUS.json',dict(status='RUNNING' if rc is None else 'COMPLETE',time=stamp(),pid=child.pid,returncode=rc))
            if not resolved and marker.exists():
                r=read(marker);assert r['pid']==proof['record']['pid'] and r['returncode']==-15 and r['status']=='FAILED'
                record=dict(marker=str(marker.relative_to(ROOT)),signature={k:r[k] for k in ['pid','returncode','status','original_log']},
                    old_log_sha256=sha(ROOT/r['original_log']),status_path=str((MOVE/'CHILD_STATUS.json').relative_to(ROOT)),
                    replacement_pid=child.pid,replacement_code_sha256=sha(SCRIPT),cause_path=str((MOVE/'RETIRED.json').relative_to(ROOT)))
                ledger=read(resume/'RESOLVED_FAILURES.json');assert not any(v['marker']==record['marker'] for v in ledger['records'])
                ledger['records'].append(record);ledger['time']=stamp();atomic(resume/'RESOLVED_FAILURES.json',ledger);resolved=True
            atomic(MOVE/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host=a.id,child=child.pid,
                old_supervisor_record_resolved=resolved,main_retained=True))
            time.sleep(15)

def old_resume():
    return next(n['source_cloud'] for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']=='legacy_0').rsplit('/',1)[0]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['retire','service']);p.add_argument('--id');a=p.parse_args();setup('vlm_repair/clone_analysis_move');globals()[a.mode](a)
