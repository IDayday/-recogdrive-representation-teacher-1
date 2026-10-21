"""Cancel only a verified redundant own queued template after its clone exists."""
from common import *
import argparse
from vlm_elastic_registry import DEST,configuration
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];body=read(folder/'REQUEST.json')
    lease=read(folder/'ADOPTED_CLONE.json');source=read(folder/'SUBMITTED.json')['job']
    assert lease['source_template_job']==source and lease['job']!=source
    p=read(ROOT/c['profile_path'])
    clone=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+lease['job'])
    assert clone['UserCommand']==body['UserCommand'] and str(clone['WorkspaceId'])==str(p['workspace_id'])
    assert clone['JobMaxRunningTimeMinutes']>=4320 and clone['Status'] not in ['Stopped','Failed','Succeeded','Deleted','Terminated']
    original=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+source)
    assert original['UserCommand']==body['UserCommand'] and original['DisplayName']==body['DisplayName']
    assert original['ResourceId']==p['quota_id'] and str(original['WorkspaceId'])==str(p['workspace_id'])
    assert original['Status']=='Queuing','This entrypoint stops queued own templates only.'
    response=request(p,'pai-dlc','2020-12-03','StopJob','POST','/api/v1/jobs/'+source+'/stop')
    assert response['JobId']==source
    atomic(folder/'TEMPLATE_CANCELLED.json',dict(status='STOP_REQUESTED_FOR_REDUNDANT_OWN_TEMPLATE',time=stamp(),
        original_job=source,adopted_clone=lease['job'],clone_status_verified=clone['Status'],
        response_job=response['JobId'],request_id=response.get('RequestId'),clone_not_stopped=True,
        original_was_queued_and_could_not_have_inflight_work=True,source_sha256=sha(Path(__file__))))
    print('OWN_QUEUED_TEMPLATE_CANCELLED',source,'QUEUED_CLONE_PRESERVED',lease['job'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);a=p.parse_args();setup('vlm_repair/clone_cancel_queued');main(a)
