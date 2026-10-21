"""Own-account queued templates, explicit clone adoption and file commands."""
from common import *
import argparse,copy,uuid
from vlm_elastic_registry import DEST,initialize,register,configuration
from vlm_elastic_cloud import request
from vlm_elastic_manage import submit,profile
from repair_queue_v2 import atomic_unique as atomic

def prepare(a):
    initialize(a.source_cloud)
    c=register('vlm_repair_v1/elastic_v1/profiles/self.json',[int(x) for x in a.devices.split(',')],a.cpu_workers,2)
    cloud=read(ROOT/a.source_cloud);body=copy.deepcopy(read(ROOT/cloud['requests'][0]));folder=ROOT/c['folder']
    body.update(DisplayName=f"sjc-vlm-clone-{a.label.lower()}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        UserCommand=f"bash {ROOT}/code/vlm_clone_launch.sh {c['id']}",JobMaxRunningTimeMinutes=4320)
    body['JobSpecs'][0]['ResourceConfig']['GPU']=str(max(c['devices'])+1);body['Settings']['JobReservedMinutes']=0
    atomic(folder/'REQUEST.json',body);atomic(folder/'PREPARED.json',dict(status='PREPARED_NOT_SUBMITTED',time=stamp(),
        label=a.label,request_sha256=sha(folder/'REQUEST.json'),clone_lease_required=True,minimum_runtime_hours=72,
        no_credential_material=True,shared_mounts_required=True))
    print('CLONE_TEMPLATE_PREPARED',a.label,c['id'],flush=True)

def adopt(a):
    c=configuration(a.id);folder=ROOT/c['folder'];source=read(folder/'SUBMITTED.json')['job']
    assert a.job!=source and a.job.startswith('dlc') and a.minutes>=4320
    path=folder/'CLONE_ACTIVATION.json';assert not path.exists(),'Keep existing clone identity immutable.'
    value=dict(status='AUTHORIZED_CLONE',time=stamp(),node=a.id,job=a.job,source_template_job=source,
        confirmed_max_minutes=a.minutes,lifetime_confirmation_source='user_clone_configuration',
        region=a.region,workspace_id=a.workspace,cloud_api_read_permission_not_assumed=True,
        original_config_sha256=sha(folder/'CONFIG.json'),original_request_sha256=sha(folder/'REQUEST.json'))
    atomic(path,value);atomic(folder/'ADOPTED_CLONE.json',value)
    print('CLONE_IDENTITY_ADOPTED',a.id,a.job,flush=True)

def command(a):
    c=configuration(a.id);folder=ROOT/c['folder'];lease=read(folder/'CLONE_ACTIVATION.json')
    script=(ROOT/a.script).resolve();assert script.is_relative_to(ROOT/'code') and script.exists()
    ident=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
    arguments=json.loads(a.arguments_json)
    assert isinstance(arguments,list) and all(isinstance(x,str) for x in arguments)
    atomic(folder/'commands/pending'/(ident+'.json'),dict(time=stamp(),expected_job=lease['job'],
        script=str(script.relative_to(ROOT)),source_sha256=sha(script),arguments=arguments,env={}))
    print('CLONE_COMMAND_ENQUEUED',a.id,ident,flush=True)

def cancel_template(a):
    c=configuration(a.id);folder=ROOT/c['folder'];lease=read(folder/'ADOPTED_CLONE.json');source=read(folder/'SUBMITTED.json')['job']
    assert source==lease['source_template_job'] and source!=lease['job']
    live=read(folder/'attestations'/lease['job']/'LIVE.json')
    assert live['job']==lease['job'] and live['authorized_clone_identity'] and live['core_pid']
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()<120
    p=profile(c);d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+source)
    body=read(folder/'REQUEST.json');assert d['UserCommand']==body['UserCommand'] and d['DisplayName']==body['DisplayName']
    assert str(d['WorkspaceId'])==str(p['workspace_id']) and d['ResourceId']==p['quota_id']
    assert d['Status'] in ['Queuing','Creating','Dequeued','WaitingConfig','Running']
    if d['Status']=='Running':
        original=read(folder/'attestations'/source/'LIVE.json');assert original['core_pid'] is None and not original['authorized_clone_identity']
    result=request(p,'pai-dlc','2020-12-03','StopJob','POST','/api/v1/jobs/'+source+'/stop')
    atomic(folder/'TEMPLATE_CANCELLED.json',dict(status='STOP_REQUESTED_FOR_REDUNDANT_OWN_TEMPLATE',time=stamp(),
        original_job=source,adopted_clone=lease['job'],response_job=result['JobId'],request_id=result.get('RequestId'),clone_not_stopped=True))
    print('OWN_QUEUED_TEMPLATE_CANCELLED',source,'CLONE_RETAINED',lease['job'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','submit','adopt','command','cancel_template']);p.add_argument('--id');p.add_argument('--label');p.add_argument('--job');p.add_argument('--minutes',type=int)
    p.add_argument('--region',default='cn-wulanchabu');p.add_argument('--workspace',default='245760');p.add_argument('--script');p.add_argument('--cpu-workers',type=int,default=80)
    p.add_argument('--devices',default=','.join(map(str,range(16))));p.add_argument('--source-cloud',default='vlm_repair_v1/resume/20261017T035006/CLOUD_READY.json');p.add_argument('--arguments-json',default='[]')
    a=p.parse_args();setup('vlm_repair/clone_manage')
    for path,h in read(DEST/'CLONE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    submit(configuration(a.id)) if a.mode=='submit' else globals()[a.mode](a)
