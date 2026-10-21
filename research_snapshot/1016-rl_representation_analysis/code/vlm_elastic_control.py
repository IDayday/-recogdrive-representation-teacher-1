"""Replace only idle acceptance waiters; leave DLC masters and compute alive."""
from common import *
import argparse,psutil,subprocess,traceback,fcntl
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

CONTROLLERS={
    'vlm_postcompute.py':DEST.parent/'POSTCOMPUTE_REVIEW_READY.json',
    'vlm_all_finalize.py':DEST.parent/'ALL_BATCHES_ANALYSES_REVIEW_READY.json',
    'vlm_four_finalize.py':DEST.parent/'ALL_FOUR_BATCHES_ANALYSES_REVIEW_READY.json',
    'vlm_five_finalize.py':DEST.parent/'ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY.json'}

def processes():
    found={}
    for p in psutil.process_iter(['pid','cwd','cmdline']):
        try:
            if p.info['cwd']!=str(ROOT):continue
            scripts=[Path(x).name for x in p.info['cmdline'] or [] if str(x).endswith('.py')]
            names=[name for name in scripts if name in CONTROLLERS]
            if len(names)==1 and 'vlm_elastic_entry.py' not in scripts:found.setdefault(names[0],[]).append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return found

def retire(a):
    folder=DEST/'control_cutover';folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'RETIRED.json').exists()
    # This version intentionally handles WAITERS only. If any statistical
    # acceptor is already running, wait for that work rather than kill it.
    assert not (DEST.parent/'final/PRIMARY_INFERENCE_COMPLETE.json').exists()
    found=processes();targets=[];children=[]
    for name,marker in CONTROLLERS.items():
        if marker.exists():continue
        values=found.get(name,[]);assert len(values)==1,(name,[p.pid for p in values])
        p=values[0];subs=p.children(recursive=True)
        expected={'vlm_all_finalize.py':'vlm_late_ungated.py','vlm_four_finalize.py':'vlm_qneighbor_ungated.py'}
        for child in subs:
            cmd=child.cmdline();assert name in expected and any(Path(x).name==expected[name] for x in cmd),('Active non-waiter child',name,child.pid)
            assert not child.children();children.append(child)
        targets.append(p)
    records=[]
    for p in targets+children:
        records.append(dict(pid=p.pid,created=p.create_time(),cmdline=p.cmdline(),cwd=p.cwd()))
    atomic(folder/'INTENT.json',dict(status='VERIFIED_IDLE_ACCEPTANCE_WAITERS_ONLY',time=stamp(),records=records,
        legacy_resume=a.legacy_resume,compute_and_DLC_masters_untouched=True))
    # Parents first: their historical child supervisors must not mistake the
    # deliberate termination of an ungated waiter for a scientific failure.
    for p in targets+children:
        expected=next(x for x in records if x['pid']==p.pid)
        assert p.create_time()==expected['created'] and p.cmdline()==expected['cmdline']
        p.terminate()
    gone,alive=psutil.wait_procs(targets+children,timeout=10);assert not alive,[p.pid for p in alive]
    atomic(folder/'RETIRED.json',dict(status='PASS',time=stamp(),records=records,legacy_resume=a.legacy_resume,
        main_GPU_full_grid_and_DLC_job_processes_untouched=True,only_idle_acceptance_waiters_replaced=True))
    print('ELASTIC_IDLE_WAITERS_RETIRED',len(targets),len(children),flush=True)

def service(a):
    c=configuration(a.id);node=ROOT/c['folder'];assert read(node/'PREFLIGHT.json')['status']=='PASS'
    proof=read(DEST/'control_cutover/RETIRED.json');resume=ROOT/proof['legacy_resume']
    folder=(ROOT/a.folder).resolve();assert folder.is_relative_to(DEST);folder.mkdir(parents=True,exist_ok=False)
    children={};streams=[]
    with (DEST/'acceptance_service.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name,marker in CONTROLLERS.items():
            if marker.exists():continue
            stream=(folder/(name+'.log')).open('a');streams.append(stream)
            env=dict(os.environ,VLM_ELASTIC_CONTROLLER_FOLDER=str(folder))
            children[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_entry.py'),'--script',name],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),host_node=a.id,processes={name:dict(pid=p.pid,created=psutil.Process(p.pid).create_time()) for name,p in children.items()},retirement_proof_sha256=sha(DEST/'control_cutover/RETIRED.json')))
        ready=False;resolved=False
        while True:
            for name,p in children.items():
                rc=p.poll();assert rc in [None,0],(name,rc)
                if rc==0:assert CONTROLLERS[name].exists(),name
                atomic(folder/'states'/(name+'.json'),dict(status='RUNNING' if rc is None else 'COMPLETE',time=stamp(),pid=p.pid,returncode=rc))
            if not ready and all((folder/'adapter_ready'/name).exists() for name in children):
                for name,p in children.items():assert read(folder/'adapter_ready'/name)['pid']==p.pid
                atomic(DEST/'DYNAMIC_ACCEPTANCE_READY.json',dict(status='PASS',time=stamp(),host_node=a.id,
                    folder=str(folder.relative_to(ROOT)),controllers={name:p.pid for name,p in children.items()},
                    legacy_equivalence_sha256=sha(DEST/'LEGACY_ACCEPTANCE_EQUIVALENCE.json'),no_frozen_numerical_source_changed=True))
                ready=True
            marker=resume/'node0/failures/postcompute.json'
            if not resolved and marker.exists() and 'vlm_postcompute.py' in children:
                r=read(marker);old=next(x for x in proof['records'] if any(Path(z).name=='vlm_postcompute.py' for z in x['cmdline']))
                assert r['pid']==old['pid'] and r['returncode']==-15 and r['status']=='FAILED'
                oldlog=ROOT/r['original_log'];record=dict(marker=str(marker.relative_to(ROOT)),
                    signature={k:r[k] for k in ['pid','returncode','status','original_log']},old_log_sha256=sha(oldlog),
                    status_path=str((folder/'states/vlm_postcompute.py.json').relative_to(ROOT)),
                    replacement_pid=children['vlm_postcompute.py'].pid,replacement_code_sha256=sha(ROOT/'code/vlm_postcompute.py'),
                    cause_path=str((DEST/'control_cutover/RETIRED.json').relative_to(ROOT)))
                ledger=read(resume/'RESOLVED_FAILURES.json');assert not any(x['marker']==record['marker'] for x in ledger['records'])
                ledger['records'].append(record);ledger['time']=stamp();atomic(resume/'RESOLVED_FAILURES.json',ledger);resolved=True
            atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host_node=a.id,
                dynamic_acceptance_ready=ready,legacy_supervisor_failure_explicitly_resolved=resolved,retained=True))
            time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['retire','service','plan']);p.add_argument('--id');p.add_argument('--folder');p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006');a=p.parse_args();setup('vlm_repair/elastic_control')
    if a.mode=='plan':print(json.dumps({name:[dict(pid=p.pid,created=p.create_time()) for p in values] for name,values in processes().items()}))
    else:
        try:globals()[a.mode](a)
        except BaseException as error:
            atomic(DEST/'failures'/f'control_{a.mode}.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
