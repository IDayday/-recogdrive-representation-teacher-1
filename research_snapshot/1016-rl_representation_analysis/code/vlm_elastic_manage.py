"""Prepare/submit one 72-hour node at a time; no stop/release operation exists."""
from common import *
import argparse,copy
from vlm_elastic_registry import DEST,configuration,initialize,register
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

def profile(c):
    p=ROOT/c['profile_path'];assert sha(p)==c['profile_sha256'];d=read(p)
    assert not any(k.lower() in {'accesskeyid','accesskeysecret','securitytoken','password'} for k in d)
    assert str(d['workspace_id']).isdigit() and d['quota_id'].startswith('quota'),'Replace the example profile with verified nonsecret workspace/quota identifiers.'
    assert d['auth']['kind'] in ['instance_role','environment','json_file']
    return d

def prepare(a):
    initialize(a.source_cloud)
    c=register(a.profile,[int(x) for x in a.devices.split(',')],a.cpu_workers,a.cpu_threads)
    p=profile(c);source=read(ROOT/a.source_cloud);body=copy.deepcopy(read(ROOT/source['requests'][0]))
    assert p['region']==os.environ['REGION'],'Use a verified regional mount/image template before crossing regions.'
    body.update(WorkspaceId=str(p['workspace_id']),ResourceId=p['quota_id'],
        DisplayName=f"sjc-vlm-elastic-{c['id']}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        JobMaxRunningTimeMinutes=c['max_running_minutes'],
        UserCommand=f"bash {ROOT}/code/vlm_elastic_launch.sh {c['id']}")
    assert len(body['JobSpecs'])==1 and int(body['JobSpecs'][0]['PodCount'])==1
    body['JobSpecs'][0]['ResourceConfig']['GPU']=str(max(c['devices'])+1)
    body['Settings']['JobReservedMinutes']=0
    assert body['JobMaxRunningTimeMinutes']>=4320
    folder=ROOT/c['folder'];atomic(folder/'REQUEST.json',body)
    atomic(folder/'PREPARED.json',dict(status='PREPARED_NOT_SUBMITTED',time=stamp(),
        request_sha256=sha(folder/'REQUEST.json'),minimum_runtime_hours=72,credential_values_stored=False,
        profile_identity_only=True,source_template_sha256=sha(ROOT/source['requests'][0]),
        submission_and_scheduling_not_yet_verified=True))
    print('ELASTIC_NODE_PREPARED_NOT_SUBMITTED',c['id'],flush=True)

def submit(c):
    p=profile(c);folder=ROOT/c['folder'];prepared=read(folder/'PREPARED.json')
    assert sha(folder/'REQUEST.json')==prepared['request_sha256']
    for path,h in read(DEST/'EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    if (folder/'SUBMITTED.json').exists():print('ALREADY_SUBMITTED',c['id']);return
    # A successful list proves only reads; CreateJob and subsequent scheduling
    # are independently verified. Do not retry an ambiguous creation blindly.
    listed=request(p,'pai-dlc','2020-12-03','ListJobs','GET','/api/v1/jobs',
        query=dict(WorkspaceId=p['workspace_id'],PageSize=100))
    body=read(folder/'REQUEST.json');existing=[j for j in listed.get('Jobs',[]) if j.get('DisplayName')==body['DisplayName']]
    assert len(existing)<=1
    response=dict(JobId=existing[0]['JobId'],adopted_same_unique_name=True) if existing else request(p,'pai-dlc','2020-12-03','CreateJob','POST','/api/v1/jobs',payload=body)
    assert response.get('JobId');atomic(folder/'SUBMITTED.json',dict(status='SUBMITTED',time=stamp(),
        job=response['JobId'],request_sha256=sha(folder/'REQUEST.json'),request_id=response.get('RequestId')))
    print('ELASTIC_NODE_SUBMITTED',c['id'],response['JobId'],flush=True)

def status(c):
    p=profile(c);folder=ROOT/c['folder'];submission=read(folder/'SUBMITTED.json')
    d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+submission['job']);body=read(folder/'REQUEST.json')
    assert str(d['WorkspaceId'])==str(p['workspace_id']) and d['ResourceId']==p['quota_id']
    assert d['UserCommand']==body['UserCommand'] and d['DisplayName']==body['DisplayName']
    assert d['JobMaxRunningTimeMinutes']>=4320,'Server did not retain the requested >=72h lifetime.'
    created=dt.datetime.fromisoformat(d['GmtCreateTime'].replace('Z','+00:00'));deadline=created+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
    result=dict(status=d['Status'],time=stamp(),id=c['id'],job=d['JobId'],maximum_minutes=d['JobMaxRunningTimeMinutes'],
        deadline=deadline.isoformat(),remaining_seconds=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds(),
        pods=[dict(id=x['PodId'],status=x['Status']) for x in d.get('Pods',[])],
        server_72h_verified=True,requested_cards=c['cards'],global_ranks=c['gpu_ranks'])
    atomic(folder/'CLOUD_STATUS.json',result);print(json.dumps(result),flush=True)

def enable(c):
    folder=ROOT/c['folder']
    assert read(folder/'GPU_SMOKE_PASS.json')['status']=='PASS'
    assert read(folder/'ENGINEERING_PASS.json')['status']=='PASS'
    assert read(DEST/'DYNAMIC_ACCEPTANCE_READY.json')['status']=='PASS'
    assert (DEST.parent/'final/PRIMARY_STAGES_APPENDED.json').exists(),'Keep the current complete validation frozen through its natural boundary.'
    if (folder/'GPU_ENABLED.json').exists():print('ALREADY_ENABLED',c['id']);return
    from vlm_elastic_registry import BASE
    tasks=read(BASE/'tasks.json');done={p.stem for p in (BASE/'receipts').glob('*.json')}
    atomic(folder/'GPU_ENABLED.json',dict(status='ENABLED',time=stamp(),id=c['id'],
        ranks=c['gpu_ranks'],cards=c['cards'],config_sha256=sha(folder/'CONFIG.json'),
        tasks_snapshot_sha256=digest(tasks),pending_tasks_at_join=sum(t['id'] not in done for t in tasks),
        no_model_seed_operator_or_score_change=True,join_after_complete_primary_validation=True))
    print('ELASTIC_GPU_ENABLED',c['id'],c['gpu_ranks'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','submit','status','enable']);p.add_argument('--id')
    p.add_argument('--profile');p.add_argument('--source-cloud',default='vlm_repair_v1/resume/20261017T035006/CLOUD_READY.json')
    p.add_argument('--devices',default=','.join(map(str,range(16))));p.add_argument('--cpu-workers',type=int,default=80);p.add_argument('--cpu-threads',type=int,default=2)
    a=p.parse_args();setup('vlm_repair/elastic_manage');prepare(a) if a.mode=='prepare' else globals()[a.mode](configuration(a.id))
