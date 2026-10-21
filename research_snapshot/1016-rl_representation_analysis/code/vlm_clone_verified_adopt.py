"""Bind an explicitly supplied clone only after actual read-only cloud verification."""
from common import *
import argparse
from vlm_elastic_registry import DEST,configuration
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];body=read(folder/'REQUEST.json')
    for p,h in read(DEST/'CLONE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    source=read(folder/'SUBMITTED.json')['job'];assert a.job!=source and a.job.startswith('dlc')
    profile=read(DEST/'profiles/self.json')
    d=request(profile,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+a.job)
    assert d['JobId']==a.job and str(d['WorkspaceId'])==str(profile['workspace_id'])
    assert d['UserCommand']==body['UserCommand'] and d['JobMaxRunningTimeMinutes']>=4320
    assert d['Status'] not in ['Stopped','Failed','Succeeded','Deleted','Terminated']
    proof=dict(status='PASS',time=stamp(),job=a.job,node=a.id,cloud_status=d['Status'],
        max_minutes=d['JobMaxRunningTimeMinutes'],created=d['GmtCreateTime'],running=d.get('GmtRunningTime'),
        user_command_verified=True,workspace_verified=True,own_DSW_role_can_read_clone=True,
        pods=[dict(id=x['PodId'],status=x['Status']) for x in d.get('Pods',[])])
    atomic(folder/'CLONE_CLOUD_VERIFIED.json',proof)
    path=folder/'CLONE_ACTIVATION.json';assert not path.exists(),'Keep clone identity immutable.'
    value=dict(status='AUTHORIZED_CLONE',time=stamp(),node=a.id,job=a.job,source_template_job=source,
        confirmed_max_minutes=d['JobMaxRunningTimeMinutes'],lifetime_confirmation_source='verified_GetJob',
        cloud_verification_path=str((folder/'CLONE_CLOUD_VERIFIED.json').relative_to(ROOT)),
        cloud_verification_sha256=sha(folder/'CLONE_CLOUD_VERIFIED.json'),region=profile['region'],
        workspace_id=str(d['WorkspaceId']),cloud_api_read_permission_verified=True,cloud_stop_permission_not_assumed=True,
        original_config_sha256=sha(folder/'CONFIG.json'),original_request_sha256=sha(folder/'REQUEST.json'))
    atomic(path,value);atomic(folder/'ADOPTED_CLONE.json',value)
    print('VERIFIED_72H_CLONE_ADOPTED',a.id,a.job,d['Status'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--job',required=True);a=p.parse_args();setup('vlm_repair/verified_clone_adopt');main(a)
