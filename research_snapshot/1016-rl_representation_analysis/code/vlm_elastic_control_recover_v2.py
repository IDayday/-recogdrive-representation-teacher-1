"""Adopt living acceptors and restart only the failed postcompute controller."""
from common import *
import argparse,psutil,socket,fcntl,subprocess,traceback,shutil
from vlm_elastic_registry import DEST,configuration
from vlm_elastic_control import CONTROLLERS
from repair_queue_v2 import atomic_unique as atomic

def alive(record):
    try:p=psutil.Process(record['pid'])
    except psutil.NoSuchProcess:return False
    assert p.create_time()==record['created']
    return p.status()!=psutil.STATUS_ZOMBIE

def acknowledge(folder,postpid):
    proof=folder/'RECOVERY_READY.json'
    if proof.exists():return
    final=DEST.parent/'final/SCIENTIFIC_ACCEPTANCE.json'
    if not final.exists():return
    accepted=read(final);assert accepted['status']=='PASS'
    base=ROOT/'runs/vlm_global_refine_20261016_v5'
    actual={read(p)['rank'] for p in (base/'receipts').glob('final_test_a*.json')}
    assert actual and {r['rank'] for r in accepted['all_32_rank_checks']}==actual
    atomic(proof,dict(status='PASS',time=stamp(),primary_acceptance_sha256=sha(final),
        all_actual_participating_card_identities_verified=len(actual),original_rescoring_and_fulltrain_replay_passed=True,
        failed_controller_only_restarted=True,living_acceptors_adopted_without_termination=True,
        model_GPU_workers_and_full_grid_untouched=True))
    adapter=DEST/'RESOLVED_ADAPTER_FAILURES.json';old=read(adapter)
    atomic(folder/'EARLIER_ADAPTER_RESOLUTIONS.json',old)
    for item in old['records']:
        if item['marker'].endswith('control_retire.json'):
            item.update(service_status=str((folder/'STATUS.json').relative_to(ROOT)),service_pid=os.getpid(),
                explanation='Original exact waiter retirement proof retained; failed validation launcher replaced after actual participating-card/scoring/full-train acceptance.')
    for path in [DEST.parent/'failures/postcompute.json',DEST/'failures/control_service.json']:
        old['records'].append(dict(marker=str(path.relative_to(ROOT)),failure_sha256=sha(path),
            proof=str(proof.relative_to(ROOT)),proof_sha256=sha(proof),service_status=str((folder/'STATUS.json').relative_to(ROOT)),service_pid=os.getpid(),
            explanation='Frozen runpy direct acceptor redefined the old fixed-32 check. v2 calls the same imported original main with dynamic checks; actual primary acceptance passed.'))
    old['time']=stamp();atomic(adapter,old)
    marker=DEST/'nodes/elastic_002/command_failures/20261017T091101_5ac0ca60.json';actual=read(marker)
    assert actual['pid']==8978 and actual['returncode']==1
    ledger=DEST/'RESOLVED_COMMAND_FAILURES.json';commands=read(ledger)
    atomic(folder/'EARLIER_COMMAND_RESOLUTIONS.json',commands)
    commands['records'].append(dict(marker=str(marker.relative_to(ROOT)),
        signature={k:actual[k] for k in ['status','job','pid','returncode','log']},log_sha256=sha(ROOT/actual['log']),
        proof=str(proof.relative_to(ROOT)),proof_sha256=sha(proof),replacement_state=str((folder/'STATUS.json').relative_to(ROOT)),replacement_pid=os.getpid(),
        cause='Only failed acceptance supervisor replaced after independently accepted original final test. No inference/grid result was replaced.'))
    commands['time']=stamp();atomic(ledger,commands)
    resume=DEST.parent/'resume/20261017T035006';path=resume/'RESOLVED_FAILURES.json';history=read(path)
    atomic(folder/'EARLIER_LEGACY_RESOLUTIONS.json',history)
    for item in history['records']:
        if item['marker'].endswith('node0/failures/postcompute.json'):
            item.update(status_path=str((folder/'states/vlm_postcompute.py.json').relative_to(ROOT)),replacement_pid=postpid,
                cause_path=str(proof.relative_to(ROOT)))
    history['time']=stamp();atomic(path,history)
    atomic(folder/'RESOLUTIONS_UPDATED.json',dict(status='PASS',time=stamp(),exact_failure_signatures_only=True))

def main(a):
    setup('vlm_repair/acceptor_recover_v2');c=configuration(a.id);lease=read(ROOT/c['folder']/'ADOPTED_CLONE.json')
    assert a.id=='elastic_002' and socket.gethostname().startswith(lease['job'])
    for p,h in read(DEST/'ACCEPTOR_RECOVERY_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    previous=read(DEST/'DYNAMIC_ACCEPTANCE_READY.json');old=ROOT/previous['folder'];launched=read(old/'LAUNCHED.json')
    assert previous['controllers']['vlm_postcompute.py']==8979
    assert not psutil.pid_exists(8978),'Original failed supervisor must have exited.'
    folder=(ROOT/a.folder).resolve();assert folder.is_relative_to(DEST/'controllers');folder.mkdir(parents=True,exist_ok=False)
    for source,name in [(DEST.parent/'failures/postcompute.json','ORIGINAL_POSTCOMPUTE_FAILURE.json'),
                        (DEST/'failures/control_service.json','ORIGINAL_SERVICE_FAILURE.json'),
                        (DEST.parent/'postcompute/vlm_final_accept.py.log','ORIGINAL_ACCEPTOR.log')]:
        shutil.copyfile(source,folder/name)
    owned={};children={};streams=[]
    with (DEST/'acceptance_service.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name,marker in CONTROLLERS.items():
            record=launched['processes'][name]
            if name=='vlm_postcompute.py':
                assert not alive(record),'Failed postcompute must have exited before retry.'
                stream=(folder/(name+'.log')).open('a');streams.append(stream)
                env=dict(os.environ,VLM_ELASTIC_CONTROLLER_FOLDER=str(folder))
                p=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_entry_v2.py'),'--script',name],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
                children[name]=p;owned[name]=dict(pid=p.pid,created=psutil.Process(p.pid).create_time(),kind='restarted_failed_controller')
            else:
                assert marker.exists() or alive(record),(name,'A living original acceptor is required')
                if alive(record):
                    p=psutil.Process(record['pid']);assert p.cwd()==str(ROOT) and name in p.cmdline()
                owned[name]=dict(record,kind='adopted_without_signal')
        atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),host_node=a.id,processes=owned,old_launch_sha256=sha(old/'LAUNCHED.json')))
        while True:
            for name,record in owned.items():
                done=CONTROLLERS[name].exists()
                if name in children:assert children[name].poll() in [None,0],(name,children[name].poll())
                assert done or alive(record),(name,'Unexpected acceptor exit')
                atomic(folder/'states'/(name+'.json'),dict(status='COMPLETE' if done else 'RUNNING',time=stamp(),pid=record['pid'],returncode=0 if done else None))
            atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host_node=a.id,
                dynamic_acceptance_ready=True,legacy_supervisor_failure_explicitly_resolved=(folder/'RESOLUTIONS_UPDATED.json').exists(),retained=True,adopted_existing_acceptors=True))
            if not (folder/'PUBLISHED.json').exists() and (folder/'adapter_ready/vlm_postcompute.py').exists():
                atomic(DEST/'DYNAMIC_ACCEPTANCE_READY.json',dict(previous,time=stamp(),folder=str(folder.relative_to(ROOT)),controllers={n:r['pid'] for n,r in owned.items()},
                    corrected_direct_acceptor_dispatch=True,recovery_execution_sha256=sha(DEST/'ACCEPTOR_RECOVERY_EXECUTION.json')))
                atomic(folder/'PUBLISHED.json',dict(status='PASS',time=stamp()))
            acknowledge(folder,owned['vlm_postcompute.py']['pid'])
            time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--folder',required=True);a=p.parse_args()
    try:main(a)
    except BaseException as exc:
        atomic(DEST/'failures/acceptor_recovery_v2.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
