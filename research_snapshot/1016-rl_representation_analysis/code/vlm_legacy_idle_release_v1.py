"""Release only the explicitly authorized, idle remaining legacy job."""
from common import *
import argparse,collections,shlex,socket
from vlm_elastic_registry import DEST,BASE
from vlm_elastic_roll import legacy,get_old,outstanding,TERMINAL
from vlm_elastic_producers import MARKERS,finished
from vlm_resume_terminal import execute
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

OUT=DEST/'idle_release_review'
IDENT='legacy_1'

def idle_checks():
    assert all(finished(s) for s in MARKERS),'A scientific producer has not finished.'
    assert (DEST.parent/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json').exists()
    assert (ROOT/'vlm_semantic_v2/FULL_ANALYSIS_ACCEPTANCE_LATEST.json').exists()
    q=ROOT/'runs/vlm_late_qualification_20261017_v1'
    assert len(read(q/'tasks.json'))==len(list((q/'receipts').glob('*.json')))
    return dict(producer_markers={s:str(p.relative_to(ROOT)) for s,p in MARKERS.items()},
                all_scientific_producers_finished=True)

def probe():
    import psutil
    n=legacy(IDENT);assert socket.gethostname().startswith(n['job'])
    checks=idle_checks();runs=set();groups=collections.Counter();unknown=[]
    allowed={'vlm_resume_node_v3.py','vlm_wait_launch_v6.py','vlm_scan_queue.py',
             'vlm_scan_spare.py','vlm_scan_wave.py','vlm_scan_wave_v2.py',
             'vlm_repair_queue_v6.py','vlm_late_selection.py','vlm_late_services.py',
             'vlm_obs_gate_services.py','vlm_legacy_idle_release_v1.py','__main__.py'}
    producers=[]
    for p in psutil.process_iter(['cwd','cmdline']):
        try:
            if p.info['cwd']!=str(ROOT):continue
            cmd=p.info['cmdline'] or []
            script=next((Path(x).name for x in cmd if x.endswith('.py')),None)
            if script is None:continue
            groups[script]+=1
            if script=='vlm_repair_queue_v6.py' and '--run' in cmd:runs.add(cmd[cmd.index('--run')+1])
            if script in MARKERS:producers.append(dict(pid=p.pid,script=script,finished=finished(script)))
            elif script not in allowed:unknown.append(dict(pid=p.pid,script=script))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert not unknown,unknown
    assert all(p['finished'] for p in producers)
    assert BASE.name in runs
    queues=[]
    for name in sorted(runs):
        b=ROOT/'runs'/name;tasks=read(b/'tasks.json');complete={p.stem for p in (b/'receipts').glob('*.json')}
        assert {t['id'] for t in tasks}==complete,(name,len(tasks),len(complete))
        assert not outstanding(b,set(n['gpu_ranks'])),name
        queues.append(dict(run=name,tasks=len(tasks),receipts=len(complete),no_uncommitted_legacy_claims=True))
    atomic(OUT/'IDLE_PROOF.json',dict(status='PASS',time=stamp(),job=n['job'],hostname=socket.gethostname(),
        checks=checks,queues=queues,process_groups=dict(groups),remaining_producers=producers,
        no_process_changed_by_probe=True,probe_sha256=sha(Path(__file__))))
    print('LEGACY_IDLE_PROOF_PASS',n['job'],flush=True)

def inspect():
    command='cd '+shlex.quote(str(ROOT))+'\npython -B code/vlm_legacy_idle_release_v1.py probe'
    result=execute(DEST.parent/'resume/20261017T035006',1,command,50)
    atomic(OUT/'PROBE_TERMINAL.json',result);assert result['status']=='PASS'
    print(json.dumps(read(OUT/'IDLE_PROOF.json')),flush=True)

def stop():
    n=legacy(IDENT);p=read(OUT/'IDLE_PROOF.json');assert p['status']=='PASS' and p['job']==n['job']
    assert p['probe_sha256']==sha(Path(__file__))
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(p['time'])).total_seconds()<120
    idle_checks()
    for q in p['queues']:
        b=ROOT/'runs'/q['run'];assert len(read(b/'tasks.json'))==len(list((b/'receipts').glob('*.json')))
        assert not outstanding(b,set(n['gpu_ranks']))
    profile,d=get_old(n);assert d['Status']=='Running'
    atomic(OUT/'AUTHORIZED_STOP.json',dict(time=stamp(),job=n['job'],idle_proof_sha256=sha(OUT/'IDLE_PROOF.json'),
        authorization='User: 有个旧节点怎么还在运行？上面还有没有任务了？没有的话你主动停了吧；有任务的话不用停。',
        only_remaining_legacy_job=True,new_72h_jobs_and_queues_retained=True,no_replacement_submission_requested=True))
    response=request(profile,'pai-dlc','2020-12-03','StopJob','POST','/api/v1/jobs/'+n['job']+'/stop')
    atomic(OUT/'STOP_RESPONSE.json',dict(time=stamp(),job=response['JobId'],request_id=response.get('RequestId')))
    print('AUTHORIZED_IDLE_LEGACY_STOP_SENT',n['job'],flush=True)

def confirm():
    n=legacy(IDENT);assert read(OUT/'STOP_RESPONSE.json')['job']==n['job'];checks=[]
    end=time.monotonic()+300
    while len(checks)<2:
        _,d=get_old(n);pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]
        if d['Status'] in TERMINAL and all(p['status'] in TERMINAL for p in pods):
            checks.append(dict(time=stamp(),job=n['job'],status=d['Status'],pods=pods))
        else:checks=[]
        assert time.monotonic()<end,'Await actual job/pod termination; do not resubmit stop.'
        if len(checks)<2:time.sleep(10)
    proof=dict(status='PASS',time=stamp(),legacy_id=IDENT,job=n['job'],double_terminal_checks=checks,
        no_shared_queue_reconcile_required=True,no_inflight_work_discarded=True,
        stop_authorization_sha256=sha(OUT/'AUTHORIZED_STOP.json'),idle_proof_sha256=sha(OUT/'IDLE_PROOF.json'),
        end_reason='User-authorized release after all scientific producers and owned queues finished.')
    atomic(OUT/'TERMINAL_CONFIRMED.json',proof);atomic(DEST/'retirements'/(IDENT+'.json'),proof)
    print('LEGACY_IDLE_RELEASE_DOUBLE_TERMINAL_CONFIRMED',n['job'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['probe','inspect','stop','confirm']);a=p.parse_args()
    setup('vlm_repair/legacy_idle_release');OUT.mkdir(exist_ok=True)
    globals()[a.mode]()
