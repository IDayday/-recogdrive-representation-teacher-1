"""Prepare continuation only after both original jobs have actually terminated.

No stop/release call exists here. Completed outputs are immutable; unreceipted
complete outputs are verified and adopted, and stale claims are archived.
"""
from common import *
import argparse
import shutil
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
from vlm_quiescence import assert_quiescent
from vlm_event_watch_v2 import errors

OLD = ['dlcmi53bf3ah2c2s', 'dlcms4op7agqj50d']
TERMINAL = {'Succeeded', 'Failed', 'Stopped', 'Deleted', 'Terminated'}
DEST = VOUT/'resume'
RUNS = ['vlm_repair_20261016_v2', 'vlm_global_refine_20261016_v5',
        'vlm_semantic_20261016_v2']

def old_status():
    from cloud_api import request
    result=[]
    for job in OLD:
        d=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        assert str(d['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
        result.append(dict(job=job,status=d['Status'],display=d['DisplayName'],
            pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]))
    return result

def move(path,archive):
    if path.exists():
        target=archive/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        assert not target.exists();shutil.move(str(path),str(target))

def repair_result(base,task,path):
    import numpy as np
    r=read(path);assert r['status']=='COMPLETE' and r['task']==task
    panel=read(base/'stages'/task['stage']/'panel.json')
    arms=read(base/'stages'/task['stage']/'arms.json')[task['arm_start']:task['arm_end']]
    rows=panel[task['start']:task['end']]
    expected={(v['token'],a,j) for v in rows for a in ['baseline']+[a['id'] for a in arms] for j in task['seeds']}
    assert len(r['records'])==len(expected)
    assert {(v['token'],v['arm'],v['seed_index']) for v in r['records']}==expected
    caps={a['id']:a['cap'] for a in arms}
    for v in r['records']:
        assert v['seed']==seed(v['token'],v['seed_index'])
        assert np.asarray(v['trajectory']).shape==(8,3) and np.isfinite(v['trajectory']).all()
        assert all(np.isfinite(x) and 0<=x<=1+1e-8 for x in v['score'].values())
        assert v['quality']==quality(v['score']['score'])
        assert v['edit']['relative_edit_max']<=caps.get(v['arm'],0)+1e-6
    return r

def semantic_result(base,task,path):
    import numpy as np
    r=read(path);assert r['status']=='COMPLETE' and r['task']==task
    source=ROOT/r['array_path'];assert sha(source)==r['array_sha256']
    rows=read(base/'panel.json')[task['start']:task['end']]
    assert [x['token'] for x in r['records']]==[x['token'] for x in rows]
    with np.load(source) as a:
        assert np.array_equal(a['global_indices'],[x['global_index'] for x in rows])
        assert len(a.files)==33
        for name in a.files:
            if name!='global_indices':assert a[name].shape[:2]==(len(rows),2) and np.isfinite(a[name]).all()
    return r

def scan_result(base,task,path):
    r=read(path);assert r['cell']==task['cell'] and r['status'] in ['COMPLETE','INELIGIBLE']
    proof=read(base.parent/'cells'/(task['cell']+'.json'));assert r['source_sha256']==proof['sha256']
    for name in ['array','moment']:
        if name+'_path' in r:assert sha(ROOT/r[name+'_path'])==r[name+'_sha256']
    return r

def reconcile(base,archive,semantic=False,cpu=False):
    if not (base/'tasks.json').exists():return dict(base=str(base.relative_to(ROOT)),absent=True)
    tasks={t['id']:t for t in read(base/'tasks.json')};out=dict(base=str(base.relative_to(ROOT)),adopted=[],requeued=[],preserved=[])
    for directory in sorted((base/'claims').glob('*')):
        if not directory.is_dir():continue
        owner=read(directory/'OWNER.json') if (directory/'OWNER.json').exists() else {}
        if owner.get('status')=='SCHEDULER_RESERVED' or owner.get('scheduler'):
            out['preserved'].append(directory.name);continue
        if semantic and owner.get('rank')==32:
            out['preserved'].append(directory.name);continue  # DSW is not being restarted.
        task=tasks[directory.name];receipt=base/'receipts'/(directory.name+'.json')
        if receipt.exists():continue
        result=base/'results'/receipt.name
        if result.exists():
            value=(scan_result(base,task,result) if cpu else semantic_result(base,task,result) if semantic else repair_result(base,task,result))
            atomic(receipt,dict(status='COMPLETE',time=stamp(),rank=value.get('rank',owner.get('rank')),
                task=task,result_sha256=sha(result),resumed_adoption=True,
                original_owner=owner,original_result_time=value.get('time'),seconds=None))
            out['adopted'].append(directory.name)
        else:
            move(directory,archive);out['requeued'].append(directory.name)
    return out

def stale_state(base,archive,keep_rank32=False):
    # Old smoke files must never certify newly assigned devices.
    for name in ['workers','smoke']:
        for path in (base/name).glob('rank*.json'):
            if keep_rank32 and path.stem=='rank032':continue
            move(path,archive)
    for node in [0,1]:
        move(base/f'node{node}/SMOKE_PASS.json',archive)
        move(base/f'node{node}/PREFLIGHT.json',archive)

def prepare():
    states=assert_quiescent()[-1]["jobs"]
    failures=errors()
    for run in RUNS:failures+=list((ROOT/'runs'/run/'failures').glob('*.json'))
    assert not failures, 'Review original failures before preparing continuation: '+str(failures[:3])
    tag=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');archive=DEST/tag
    archive.mkdir(parents=True,exist_ok=False);atomic(archive/'OLD_JOB_TERMINATION.json',dict(time=stamp(),jobs=states))
    changes=[]
    for run in RUNS:
        base=ROOT/'runs'/run;sem='semantic' in run
        changes.append(reconcile(base,archive/'stale_state',semantic=sem));stale_state(base,archive/'stale_state',keep_rank32=sem)
    for root in [VOUT,ROOT/'vlm_semantic_v2']:
        for kind in ['scan','rapid']:
            base=root/kind
            changes.append(reconcile(base,archive/'stale_state',cpu=True));stale_state(base,archive/'stale_state')
    # Independent launch logs and container identities; never replace old requests.
    requests=[]
    for node in [0,1]:
        request=read(ROOT/f'dlc/candidate_repair_request_node{node}.json')
        request.update(DisplayName=f'sjc-vlm-continuation-node{node}-{tag.lower()}',
            UserCommand=f'bash {ROOT}/code/vlm_resume_launch_v2.sh {node} {archive.relative_to(ROOT)}',
            JobMaxRunningTimeMinutes=720)
        request['Settings']['JobReservedMinutes']=0
        path=archive/f'request_node{node}.json';atomic(path,request);requests.append(str(path.relative_to(ROOT)))
    plan=dict(status='PREPARED_NOT_SUBMITTED',time=stamp(),old_jobs=states,requests=requests,
        resume_directory=str(archive.relative_to(ROOT)),changes=changes,do_not_stop_or_release=True,
        preemption_rule='Only actual old-job termination authorizes this continuation; no reset of old running limits.',
        repair_implementation='Frozen Queue6 exact-equivalent old-region mathematics; old completed Queue2 results unchanged.',
        equivalence_sha256=sha(VOUT/'V6_EQUIVALENCE.json'))
    atomic(archive/'PREPARED.json',plan);atomic(DEST/'LATEST.json',dict(path=str(archive.relative_to(ROOT)),status=plan['status']))
    print(json.dumps(dict(status=plan['status'],path=plan['resume_directory'],changes=[dict(base=x['base'],adopted=len(x.get('adopted',[])),requeued=len(x.get('requeued',[]))) for x in changes])),flush=True)

def submit():
    from cloud_api import request
    folder=ROOT/read(DEST/'LATEST.json')['path'];p=read(folder/'PREPARED.json')
    assert_quiescent()
    for node,path in enumerate(p['requests']):
        receipt=folder/f'submission_node{node}.json'
        if receipt.exists():continue
        response=request('pai-dlc','2020-12-03','CreateJob','POST','/api/v1/jobs',payload=read(ROOT/path))
        atomic(receipt,response);assert response.get('JobId')
    jobs=[read(folder/f'submission_node{n}.json')['JobId'] for n in [0,1]]
    atomic(folder/'CLOUD_READY.json',dict(status='SUBMITTED',time=stamp(),jobs=jobs,requests=p['requests'],retention='Keep running until platform limit; no release/stop.'))
    print(json.dumps(dict(status='SUBMITTED',jobs=jobs)),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['status','prepare','submit']);args=a.parse_args();setup('vlm_repair/resume')
    if args.mode=='status':print(json.dumps(old_status()))
    else:globals()[args.mode]()
