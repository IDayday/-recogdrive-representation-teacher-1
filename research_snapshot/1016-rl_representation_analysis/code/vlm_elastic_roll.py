"""Explicit rolling replacement of legacy jobs after completed in-flight work.

Never reconciles the whole shared queue. Extra nodes can keep computing.
"""
from common import *
import argparse,psutil,signal,socket,fcntl
from vlm_elastic_registry import DEST,BASE
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

TERMINAL={'Succeeded','Failed','Stopped','Deleted','Terminated','Completed'}
PRODUCERS={'vlm_final_driver.py','vlm_semantic_repair_v3.py','vlm_ungated_final.py',
           'vlm_late_repair.py','vlm_qneighbor_repair_v2.py','vlm_obs_gate_test.py','vlm_obs_qda_gate.py'}
SUPERVISORS={'vlm_repair_queue_v6.py','vlm_scan_queue.py','vlm_scan_spare.py',
             'vlm_scan_wave.py','vlm_scan_wave_v2.py','vlm_late_services.py',
             'vlm_late_selection.py','vlm_obs_gate_services.py'}

def legacy(ident):
    n=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']==ident)
    assert n['kind']=='legacy';return n

def ready():
    v=DEST.parent;required=[v/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json',
        v/'FINAL_ANALYSES_REVIEW_READY.json',DEST/'DYNAMIC_ACCEPTANCE_READY.json',
        v/'late_token_coverage/SELECTION_LOCK.json']
    missing=[str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if not any((v/'late_token_coverage'/x).exists() for x in ['FITS_READY.json','NO_COMPETITIVE_CANDIDATES.json']):missing.append('late fits not ready')
    q=ROOT/'runs/vlm_late_qualification_20261017_v1'
    if (q/'tasks.json').exists() and len(read(q/'tasks.json'))!=len(list((q/'receipts').glob('*.json'))):missing.append('late qualification in flight')
    p=DEST/'DYNAMIC_ACCEPTANCE_READY.json'
    if p.exists():
        service=ROOT/read(p)['folder']/'STATUS.json'
        if not service.exists() or (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(read(service)['time'])).total_seconds()>120:missing.append('acceptance service heartbeat is not fresh')
    return missing

def process_doc(p,kind,run=None,rank=None):
    return dict(pid=p.pid,created=p.create_time(),cmdline=p.cmdline(),kind=kind,run=run,rank=rank)

def restore(records):
    for r in records:
        try:p=psutil.Process(r['pid'])
        except psutil.NoSuchProcess:continue
        assert p.create_time()==r['created'] and p.cmdline()==r['cmdline'] and p.cwd()==str(ROOT)
        p.send_signal(signal.SIGCONT)

def outstanding(base,ranks):
    complete={p.stem for p in (base/'receipts').glob('*.json')};values=[]
    for p in (base/'claims').iterdir():
        if p.name in complete:continue
        owner=p/'OWNER.json'
        if not owner.exists():values.append(dict(task=p.name,owner_unknown=True));continue
        r=read(owner)
        if r.get('rank') in ranks:values.append(dict(task=p.name,rank=r['rank'],pid=r.get('pid')))
    return values

def quiesce(a):
    n=legacy(a.legacy_id);assert socket.gethostname().startswith(n['job'])
    folder=(ROOT/a.folder).resolve();assert folder.is_relative_to(DEST/'rolling');folder.mkdir(parents=True,exist_ok=False)
    missing=ready()
    if missing:atomic(folder/'DEFERRED.json',dict(status='DEFERRED_NO_PROCESS_CHANGED',time=stamp(),missing=missing));print('ROLLING_DEFERRED',missing);return
    targets=[]
    for p in psutil.process_iter(['cwd','cmdline']):
        try:
            cmd=p.info['cmdline'] or []
            if p.info['cwd']!=str(ROOT):continue
            script=next((Path(z).name for z in cmd if str(z).endswith('.py')),None)
            if script=='vlm_repair_queue_v6.py' and 'worker' in cmd:
                rank=int(cmd[cmd.index('--rank')+1]);run=cmd[cmd.index('--run')+1]
                if rank in n['gpu_ranks']:targets.append((p,'gpu',run,rank))
            elif script in PRODUCERS:targets.append((p,'producer',None,None))
            elif script in SUPERVISORS and '--rank' not in cmd:targets.append((p,'supervisor',None,None))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert {rank for _,kind,run,rank in targets if kind=='gpu' and run==BASE.name}==set(n['gpu_ranks'])
    paused=[];pending=list(targets);began=time.monotonic()
    try:
        while pending and time.monotonic()-began<25:
            for item in list(pending):
                p,kind,run,rank=item
                if not p.is_running():pending.remove(item);continue
                if kind=='supervisor' and any(x[1]!='supervisor' for x in pending):continue
                if kind in ['producer','supervisor']:
                    if kind=='producer' and any(x.status()!=psutil.STATUS_ZOMBIE for x in p.children(recursive=True)):continue
                    if 'hrtimer_nanosleep' not in Path(f'/proc/{p.pid}/wchan').read_text():continue
                else:
                    state=ROOT/'runs'/run/'workers'/f'rank{rank:03d}.json'
                    if not state.exists() or read(state)['status'] not in ['QUEUE_WAIT','RUNNING']:continue
                r=process_doc(p,kind,run,rank);p.send_signal(signal.SIGSTOP)
                if kind=='gpu' and outstanding(ROOT/'runs'/run,{rank}):p.send_signal(signal.SIGCONT);continue
                paused.append(r);pending.remove(item)
            if pending:time.sleep(.25)
        if pending:
            restore(paused);atomic(folder/'DEFERRED.json',dict(status='DEFERRED_ALL_PAUSES_REVERSED',time=stamp(),
                remaining=[process_doc(*x) for x in pending],no_inflight_work_discarded=True));print('ROLLING_DEFERRED_BUSY_ALL_RESUMED');return
        for run in {x['run'] for x in paused if x['kind']=='gpu'}:assert not outstanding(ROOT/'runs'/run,set(n['gpu_ranks']))
        # Every old writer is asleep and paused. Reject an append half-commit
        # instead of editing any registry while other nodes are still alive.
        with (BASE/'queue.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);tasks=read(BASE/'tasks.json')
            for p in (BASE/'stages').glob('*/PROTOCOL.json'):
                assert sum(t['stage']==p.parent.name for t in tasks)==read(p)['tasks']
        atomic(folder/'QUIESCED.json',dict(status='PASS',time=stamp(),legacy_id=n['id'],job=n['job'],
            ranks=n['gpu_ranks'],paused_processes=paused,all_old_GPU_claims_committed=True,
            old_heavy_CPU_tasks_finished=True,no_global_claim_requeue_or_output_mutation=True,
            queue_snapshot_sha256=digest(tasks),must_stop_or_explicitly_resume_promptly=True))
        print('ROLLING_QUIESCED_NO_INFLIGHT_WORK',n['id'],len(paused),flush=True)
    except BaseException:
        restore(paused);raise

def get_old(n):
    profile=read(DEST/'profiles/self.json');d=request(profile,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+n['job'])
    cloud=read(ROOT/n['source_cloud']);index=cloud['jobs'].index(n['job']);body=read(ROOT/cloud['requests'][index])
    assert d['UserCommand']==body['UserCommand'] and str(d['WorkspaceId'])==str(profile['workspace_id'])
    return profile,d

def stop(a):
    n=legacy(a.legacy_id);folder=ROOT/a.folder;proof=read(folder/'QUIESCED.json')
    assert proof['job']==n['job'] and proof['legacy_id']==n['id'] and not ready()
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(proof['time'])).total_seconds()<120
    assert read(DEST/'USER_RESOURCE_POLICY.json')['legacy_two_job_rolling_stop_and_recreate_authorized']
    available=0;running=[]
    for node in read(DEST/'REGISTRY.json')['nodes']:
        if node['kind']!='elastic':continue
        c=read(ROOT/node['config']);f=ROOT/c['folder']
        if not (f/'GPU_ENABLED.json').exists():continue
        p=read(ROOT/c['profile_path']);job=read(f/'SUBMITTED.json')['job']
        d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        if d['Status']=='Running' and d['JobMaxRunningTimeMinutes']>=4320:available+=c['cards'];running.append(c['id'])
    assert available>=n['cards'],'First establish replacement computing capacity.'
    assert read(DEST/'DYNAMIC_ACCEPTANCE_READY.json')['host_node'] in running
    profile,d=get_old(n);assert d['Status']=='Running'
    atomic(folder/'AUTHORIZED_STOP.json',dict(time=stamp(),legacy_id=n['id'],job=n['job'],
        completed_inflight_proof_sha256=sha(folder/'QUIESCED.json'),verified_running_72h_cards=available,
        authorization='User explicitly selected rolling legacy replacement after adding nodes. New jobs still require user consent for final release.'))
    response=request(profile,'pai-dlc','2020-12-03','StopJob','POST','/api/v1/jobs/'+n['job']+'/stop')
    atomic(folder/'STOP_RESPONSE.json',dict(time=stamp(),job=response['JobId'],request_id=response.get('RequestId')))
    print('AUTHORIZED_LEGACY_ROLLING_STOP_SENT',n['job'],flush=True)

def confirm(a):
    n=legacy(a.legacy_id);folder=ROOT/a.folder;assert read(folder/'STOP_RESPONSE.json')['job']==n['job'];checks=[]
    for i in range(2):
        _,d=get_old(n);pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]
        if d['Status'] not in TERMINAL or any(p['status'] not in TERMINAL for p in pods):print('WAITING_LEGACY_TERMINAL',d['Status']);return
        checks.append(dict(time=stamp(),job=n['job'],status=d['Status'],pods=pods))
        if i==0:time.sleep(10)
    proof=dict(status='PASS',time=stamp(),legacy_id=n['id'],job=n['job'],double_terminal_checks=checks,
        no_shared_queue_reconcile_required=True,stop_authorization_sha256=sha(folder/'AUTHORIZED_STOP.json'))
    atomic(folder/'TERMINAL_CONFIRMED.json',proof);atomic(DEST/'retirements'/(n['id']+'.json'),proof)
    print('LEGACY_DOUBLE_TERMINAL_CONFIRMED',n['id'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inspect','quiesce','resume','stop','confirm']);p.add_argument('--legacy-id');p.add_argument('--folder');a=p.parse_args();setup('vlm_repair/elastic_roll')
    if a.mode=='inspect':print(json.dumps(dict(status='READ_ONLY',missing=ready(),no_stop_requested=True)),flush=True)
    elif a.mode=='resume':restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    else:globals()[a.mode](a)
