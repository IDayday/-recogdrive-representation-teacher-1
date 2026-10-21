"""Dynamic, task-owned cold continuation; never stops jobs or mutates live queues.

Prepared for a possible second expiry. Every previous job and pod must actually
be terminal twice before prepare changes claims, smoke files or append commits.
"""
from common import *
import argparse
from vlm_core import VOUT
from vlm_resume_v3 import reconcile,stale_state,move,RUNS
from vlm_resume_stage_registry_v2 import recover_stages,archive_partial_cpu
from vlm_event_watch_v2 import errors
from repair_queue_v2 import atomic_unique as atomic

TERMINAL={'Succeeded','Failed','Stopped','Deleted','Terminated','Completed'}


def status(previous):
    from cloud_api import request
    source=previous/'CLOUD_READY.json';cloud=read(source);assert len(cloud['jobs'])==2
    states=[]
    for node,job in enumerate(cloud['jobs']):
        d=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        assert str(d['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
        assert d['DisplayName'].startswith(f'sjc-vlm-continuation-node{node}-')
        assert d['UserCommand']==read(ROOT/cloud['requests'][node])['UserCommand']
        states.append(dict(job=job,status=d['Status'],display=d['DisplayName'],
            pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])],
            created=d['GmtCreateTime'],ended=d.get('GmtEndTime')))
    return states


def quiescent(previous):
    checks=[]
    for index in range(2):
        states=status(previous)
        assert all(s['status'] in TERMINAL for s in states),'A previous job is active; no queue mutation or new submission permitted.'
        assert all(p['status'] in TERMINAL for s in states for p in s['pods']),'A previous pod is still active.'
        checks.append(dict(time=stamp(),jobs=states))
        if index==0:time.sleep(10)
    return checks


def review_failures(previous):
    bad=errors()+list((VOUT/'late_token_coverage/failures').glob('*.json'))+list((VOUT/'qda_neighbor_repair/failures').glob('*.json'))+list((VOUT/'observation_qda_gate/failures').glob('*.json'))
    for node in [0,1]:bad+=list((previous/f'node{node}').glob('FAILED.json'))
    resolutions=read(previous/'RESOLVED_FAILURES.json')['records'] if (previous/'RESOLVED_FAILURES.json').exists() else []
    for node in [0,1]:
        for path in (previous/f'node{node}/failures').glob('*.json'):
            r=read(path);match=next((x for x in resolutions if x['marker']==str(path.relative_to(ROOT))),None)
            if match is None or any(r.get(k)!=v for k,v in match['signature'].items()):bad.append(path);continue
            assert sha(ROOT/r['original_log'])==match['old_log_sha256']
            assert sha(ROOT/'code/vlm_global_funnel_v6.py')==match['replacement_code_sha256']
            # Freshness belongs to the live-job monitor. Here double terminal
            # proof has established there can be no future process heartbeat.
    assert not bad,'Review retained failures before continuation: '+str(bad[:3])


def qualification_claims(archive):
    base=ROOT/'runs/vlm_late_qualification_20261017_v1';out=dict(adopted=[],requeued=[])
    if not (base/'tasks.json').exists():return out
    tasks={t['id']:t for t in read(base/'tasks.json')}
    for path in (base/'claims').glob('*'):
        receipt=base/'receipts'/(path.name+'.json')
        if receipt.exists():continue
        task=tasks[path.name];result=VOUT/'late_token_coverage/selected'/(path.name+'.json')
        if result.exists():
            r=read(result);assert r['status']=='FROZEN_FAMILY_SELECTION'
            assert r['group']==task['table']['group'] and r['pool_sha256']==task['table']['sha256']
            owner=read(path/'OWNER.json')
            atomic(receipt,dict(status='COMPLETE',time=stamp(),rank=owner['rank'],task=task,
                result_path=str(result.relative_to(ROOT)),result_sha256=sha(result),resumed_adoption=True))
            out['adopted'].append(path.name)
        else:move(path,archive);out['requeued'].append(path.name)
    return out


def prepare(previous):
    checks=quiescent(previous);review_failures(previous)
    execution=read(VOUT/'CONTINUATION_EXECUTION_v6.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    folder=VOUT/'resume'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    commits={run:recover_stages(ROOT/'runs'/run,folder) for run in RUNS[:2]}
    partial=[]
    for root in [VOUT,ROOT/'vlm_semantic_v2']:partial+=archive_partial_cpu(root,folder/'uncommitted_cpu_arrays')
    # An array without its final metadata has never been returned to a stage
    # producer. Preserve it before a different BLAS partition recomputes it.
    for directory in [VOUT/'fits',VOUT/'global_funnel/gates',VOUT/'final/fits',
                      VOUT/'qda_neighbor_repair/operator_calibration/gates']:
        for path in directory.glob('*.npz'):
            if not path.with_suffix('.json').exists():
                partial.append(str(path.relative_to(ROOT)));move(path,folder/'uncommitted_fit_arrays')
    for path in (VOUT/'late_token_coverage/work').glob('*/geometry_*.npz'):
        if not path.with_suffix('.json').exists():
            partial.append(str(path.relative_to(ROOT)));move(path,folder/'uncommitted_geometry_arrays')
    changes=[]
    for run in RUNS:
        base=ROOT/'runs'/run;semantic='semantic' in run
        changes.append(reconcile(base,folder/'stale_state',semantic=semantic));stale_state(base,folder/'stale_state',keep_rank32=semantic)
    for root in [VOUT,ROOT/'vlm_semantic_v2']:
        for kind in ['scan','rapid']:
            changes.append(reconcile(root/kind,folder/'stale_state',cpu=True));stale_state(root/kind,folder/'stale_state')
    qualification=qualification_claims(folder/'stale_state')
    for node in [0,1]:move(VOUT/f'scan_spare/node{node}',folder/'stale_aux')
    cloud=read(previous/'CLOUD_READY.json');requests=[]
    for node in [0,1]:
        body=read(ROOT/cloud['requests'][node]);body.update(
            DisplayName=f'sjc-vlm-continuation-node{node}-{folder.name.lower()}',
            UserCommand=f'bash {ROOT}/code/vlm_continuation_launch_v6.sh {node} {folder.relative_to(ROOT)}',JobMaxRunningTimeMinutes=720)
        body['Settings']['JobReservedMinutes']=0
        p=folder/f'request_node{node}.json';atomic(p,body);requests.append(str(p.relative_to(ROOT)))
    atomic(folder/'PREPARED.json',dict(status='PREPARED_NOT_SUBMITTED',time=stamp(),
        continuation_version=6,previous_resume=str(previous.relative_to(ROOT)),previous_cloud_sha256=sha(previous/'CLOUD_READY.json'),
        quiescence=checks,changes=changes,append_commits=commits,qualification=qualification,
        uncommitted_cpu_arrays_archived=partial,requests=requests,no_job_stopped_or_released=True,
        completed_outputs_untouched=True))
    atomic(VOUT/'resume/LATEST_v6.json',dict(path=str(folder.relative_to(ROOT))))
    print('DYNAMIC_CONTINUATION_PREPARED',str(folder.relative_to(ROOT)),flush=True)


def submit(folder):
    from cloud_api import request
    p=read(folder/'PREPARED.json');previous=ROOT/p['previous_resume'];quiescent(previous)
    assert sha(previous/'CLOUD_READY.json')==p['previous_cloud_sha256']
    for node,path in enumerate(p['requests']):
        receipt=folder/f'submission_node{node}.json'
        if receipt.exists():continue
        response=request('pai-dlc','2020-12-03','CreateJob','POST','/api/v1/jobs',payload=read(ROOT/path))
        assert response.get('JobId');atomic(receipt,response)
    jobs=[read(folder/f'submission_node{n}.json')['JobId'] for n in [0,1]]
    atomic(folder/'CLOUD_READY.json',dict(status='SUBMITTED',time=stamp(),jobs=jobs,requests=p['requests'],retention='Keep jobs and queues open; no in-place extension promised.'))
    print(json.dumps(dict(status='SUBMITTED',jobs=jobs)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['status','prepare','submit'])
    p.add_argument('--previous-resume');p.add_argument('--prepared');a=p.parse_args();setup('vlm_repair/continuation_v6')
    if a.mode=='submit':submit((ROOT/a.prepared).resolve())
    else:
        previous=(ROOT/a.previous_resume).resolve();assert previous.is_relative_to(VOUT/'resume')
        print(json.dumps(status(previous))) if a.mode=='status' else prepare(previous)
