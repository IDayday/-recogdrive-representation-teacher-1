"""Legacy rolling replacement using actual adopted clone capacity, never template IDs."""
from common import *
import argparse
import vlm_elastic_roll as original
from vlm_elastic_registry import DEST
from vlm_elastic_cloud import request
from vlm_clone_resource_evidence import fresh_clone
from repair_queue_v2 import atomic_unique as atomic

def stop(a):
    n=original.legacy(a.legacy_id);folder=ROOT/a.folder;proof=read(folder/'QUIESCED.json')
    assert proof['job']==n['job'] and proof['legacy_id']==n['id'] and not original.ready()
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(proof['time'])).total_seconds()<120
    assert read(DEST/'USER_RESOURCE_POLICY.json')['legacy_two_job_rolling_stop_and_recreate_authorized']
    available=0;running=[];evidence=[];self_profile=read(DEST/'profiles/self.json')
    for node in read(DEST/'REGISTRY.json')['nodes']:
        if node['kind']!='elastic':continue
        c=read(ROOT/node['config']);f=ROOT/c['folder']
        if not (f/'GPU_ENABLED.json').exists():continue
        if (f/'ADOPTED_CLONE.json').exists():
            verified=fresh_clone(c);job=verified['job'];p=self_profile
        else:
            job=read(f/'SUBMITTED.json')['job'];p=read(ROOT/c['profile_path']);verified=dict(node=c['id'],job=job,cards=c['cards'])
        d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        assert str(d['WorkspaceId'])==str(p['workspace_id']) and d['UserCommand']==read(f/'REQUEST.json')['UserCommand']
        if d['Status']=='Running' and d['JobMaxRunningTimeMinutes']>=4320:
            available+=c['cards'];running.append(c['id']);evidence.append(verified)
    assert available>=n['cards'],'First establish verified replacement computing capacity.'
    assert read(DEST/'DYNAMIC_ACCEPTANCE_READY.json')['host_node'] in running
    profile,d=original.get_old(n);assert d['Status']=='Running'
    atomic(folder/'AUTHORIZED_STOP.json',dict(time=stamp(),legacy_id=n['id'],job=n['job'],
        completed_inflight_proof_sha256=sha(folder/'QUIESCED.json'),verified_running_72h_cards=available,
        actual_clone_capacity=evidence,authorization='Explicit legacy rolling authorization; no clone or renewed job is stopped.'))
    response=request(profile,'pai-dlc','2020-12-03','StopJob','POST','/api/v1/jobs/'+n['job']+'/stop')
    atomic(folder/'STOP_RESPONSE.json',dict(time=stamp(),job=response['JobId'],request_id=response.get('RequestId')))
    print('AUTHORIZED_LEGACY_ROLLING_STOP_SENT',n['job'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inspect','quiesce','resume','stop','confirm']);p.add_argument('--legacy-id');p.add_argument('--folder');a=p.parse_args()
    setup('vlm_repair/elastic_roll_clones')
    for manifest in ['EXECUTION.json','ROLL_EXECUTION.json','CLONE_ADMIN_EXECUTION.json']:
        for path,h in read(DEST/manifest)['code_sha256'].items():assert sha(ROOT/path)==h,path
    if a.mode=='inspect':print(json.dumps(dict(status='READ_ONLY',missing=original.ready(),no_stop_requested=True)),flush=True)
    elif a.mode=='resume':original.restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    elif a.mode=='stop':stop(a)
    else:getattr(original,a.mode)(a)
