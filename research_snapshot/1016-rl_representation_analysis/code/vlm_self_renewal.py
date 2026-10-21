"""Prepare own 72-hour replacements; submit only after the corresponding old job retires."""
from common import *
import argparse,copy
from vlm_elastic_registry import DEST,configuration,register
from vlm_elastic_manage import submit,profile
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

def retirement(c):
    intent=read(ROOT/c['folder']/'RENEWAL_INTENT.json')
    proof=read(DEST/'retirements'/(intent['legacy_id']+'.json'))
    assert proof['status']=='PASS' and proof['job']==intent['legacy_job'] and len(proof['double_terminal_checks'])==2
    return intent,proof

def prepare(a):
    old=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']==a.legacy_id)
    assert old['kind']=='legacy'
    for n in read(DEST/'REGISTRY.json')['nodes']:
        if n['kind']!='elastic':continue
        f=ROOT/read(ROOT/n['config'])['folder'];p=f/'RENEWAL_INTENT.json'
        assert not p.exists() or read(p)['legacy_id']!=a.legacy_id,'A replacement is already prepared.'
    c=register('vlm_repair_v1/elastic_v1/profiles/self.json',[int(v) for v in a.devices.split(',')],a.cpu_workers,2)
    cloud=read(ROOT/old['source_cloud']);index=cloud['jobs'].index(old['job'])
    body=copy.deepcopy(read(ROOT/cloud['requests'][index]));folder=ROOT/c['folder']
    body.update(DisplayName='sjc-vlm-renewed-'+a.legacy_id.replace('_','')+'-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S'),
        UserCommand=f"bash {ROOT}/code/vlm_clone_launch.sh {c['id']}",JobMaxRunningTimeMinutes=4320)
    body['JobSpecs'][0]['ResourceConfig']['GPU']=str(max(c['devices'])+1);body['Settings']['JobReservedMinutes']=0
    atomic(folder/'REQUEST.json',body);atomic(folder/'PREPARED.json',dict(status='PREPARED_NOT_SUBMITTED',time=stamp(),
        request_sha256=sha(folder/'REQUEST.json'),own_renewal_not_a_peer_clone=True,submission_requires_old_job_double_terminal_proof=True))
    atomic(folder/'RENEWAL_INTENT.json',dict(time=stamp(),node=c['id'],legacy_id=old['id'],legacy_job=old['job'],
        runtime_kind='OWN_RENEWAL',future_minutes=4320,no_old_job_stopped=True,no_new_job_submitted=True))
    print('OWN_72H_REPLACEMENT_PREPARED_NOT_SUBMITTED',old['id'],c['id'],flush=True)

def activate(c):
    intent,proof=retirement(c);folder=ROOT/c['folder'];job=read(folder/'SUBMITTED.json')['job'];p=profile(c)
    d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job);body=read(folder/'REQUEST.json')
    assert d['JobMaxRunningTimeMinutes']>=4320 and d['UserCommand']==body['UserCommand']
    assert str(d['WorkspaceId'])==str(p['workspace_id']) and d['ResourceId']==p['quota_id']
    assert d['Status'] not in ['Stopped','Failed','Succeeded','Deleted','Terminated']
    assert not (folder/'CLONE_ACTIVATION.json').exists()
    # The frozen runner's identity gate is shared by peer clones and own
    # renewals. Explicit provenance prevents an own renewal being called a clone.
    value=dict(status='AUTHORIZED_CLONE',runtime_kind='OWN_RENEWAL',was_cloned=False,time=stamp(),node=c['id'],
        job=job,source_template_job=job,confirmed_max_minutes=d['JobMaxRunningTimeMinutes'],
        lifetime_confirmation_source='verified_GetJob',region=p['region'],workspace_id=str(d['WorkspaceId']),
        original_config_sha256=sha(folder/'CONFIG.json'),original_request_sha256=sha(folder/'REQUEST.json'),
        old_legacy_job=intent['legacy_job'],old_terminal_proof_sha256=sha(DEST/'retirements'/(intent['legacy_id']+'.json')),
        requires_user_consent_for_final_release=True)
    atomic(folder/'CLONE_ACTIVATION.json',value);atomic(folder/'ADOPTED_CLONE.json',value)
    print('OWN_RENEWAL_IDENTITY_ACTIVATED',c['id'],job,d['Status'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','submit','activate']);p.add_argument('--legacy-id');p.add_argument('--id')
    p.add_argument('--devices',default=','.join(map(str,range(16))));p.add_argument('--cpu-workers',type=int,default=80);a=p.parse_args();setup('vlm_repair/self_renewal')
    for name in ['EXECUTION.json','CLONE_EXECUTION.json','SELF_RENEWAL_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    if a.mode=='prepare':prepare(a)
    elif a.mode=='submit':c=configuration(a.id);retirement(c);submit(c)
    else:activate(configuration(a.id))
