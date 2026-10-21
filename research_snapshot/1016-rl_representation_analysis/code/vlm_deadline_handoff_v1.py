"""Drain only in the final 15 minutes; retain jobs for natural platform expiry.

Control flow copied from the verified scoped rolling quiescer, with a bounded
configurable wait and a natural-expiry policy. No cloud Stop/Delete operation.
"""
from common import *
import argparse,psutil,signal,socket,fcntl
from vlm_elastic_registry import DEST,BASE
from vlm_elastic_roll import legacy,process_doc,restore,outstanding,PRODUCERS,SUPERVISORS,get_old,TERMINAL
from vlm_elastic_roll_clones_v2 import ready
from repair_queue_v2 import atomic_unique as atomic

def drain(a):
    n=legacy(a.legacy_id);assert socket.gethostname().startswith(n['job'])
    assert 30<=a.wait_seconds<=600
    assert (DEST/'CURRENT_USER_RESOURCE_POLICY.json').exists()
    live=read(DEST/'CLONE_LIVE_LATEST.json');record=next(j for j in live['jobs'] if j['id']==a.legacy_id)
    assert record['job']==n['job'] and record['status']=='Running'
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()<360
    deadline=dt.datetime.fromisoformat(record['conservative_deadline'])
    seconds=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()
    assert 30<seconds<=900,'Drain only in the final 15 minutes; no early pause.'
    a.wait_seconds=min(a.wait_seconds,seconds-20)
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
        while pending and time.monotonic()-began<a.wait_seconds:
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
            queue_snapshot_sha256=digest(tasks),must_stop_or_explicitly_resume_promptly=False,retain_until_platform_deadline=True,platform_deadline=deadline.isoformat(),no_StopJob_or_DeleteJob_requested=True))
        print('ROLLING_QUIESCED_NO_INFLIGHT_WORK',n['id'],len(paused),flush=True)
    except BaseException:
        restore(paused);raise

def confirm(a):
    n=legacy(a.legacy_id);folder=(ROOT/a.folder).resolve();assert folder.is_relative_to(DEST/'rolling')
    proof=read(folder/'QUIESCED.json');assert proof['job']==n['job'] and proof['retain_until_platform_deadline']
    deadline=dt.datetime.fromisoformat(proof['platform_deadline'])
    assert dt.datetime.now(dt.timezone.utc)>=deadline,'Do not confirm natural expiry before the verified deadline.'
    checks=[]
    for i in range(2):
        _,d=get_old(n);pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]
        if d['Status'] not in TERMINAL or any(p['status'] not in TERMINAL for p in pods):
            print('WAIT_PLATFORM_TERMINAL',n['id'],d['Status'],flush=True);return
        checks.append(dict(time=stamp(),job=n['job'],status=d['Status'],pods=pods))
        if i==0:time.sleep(10)
    result=dict(status='PASS',time=stamp(),legacy_id=n['id'],job=n['job'],double_terminal_checks=checks,
        no_shared_queue_reconcile_required=True,no_StopJob_or_DeleteJob_requested=True,
        end_reason='Verified terminal after original platform maximum; no active release by this helper.',
        quiesced_proof_sha256=sha(folder/'QUIESCED.json'))
    atomic(folder/'TERMINAL_CONFIRMED.json',result);atomic(DEST/'retirements'/(n['id']+'.json'),result)
    print('NATURAL_EXPIRY_DOUBLE_TERMINAL_CONFIRMED',n['id'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['drain','confirm','resume'])
    p.add_argument('--legacy-id',required=True);p.add_argument('--folder',required=True)
    p.add_argument('--wait-seconds',type=float,default=600);a=p.parse_args();setup('vlm_repair/deadline_handoff')
    for name in ['EXECUTION.json','ROLL_EXECUTION.json','CLONE_ANALYSIS_MOVE_EXECUTION.json','DEADLINE_HANDOFF_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    if a.mode=='resume':restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    else:globals()[a.mode](a)
