"""Cloud-aware pending-clone monitoring; use actual clone identity and lifetime."""
from common import *
import argparse
import vlm_clone_watch as previous
from vlm_clone_watch_v2 import resolved
from vlm_elastic_registry import DEST
from vlm_elastic_cloud import request

original_age=previous.age
original_atomic=previous.atomic
CACHE={};ISSUES={}

def cloud(lease):
    job=lease['job'];cached=CACHE.get(job)
    if cached and time.monotonic()-cached[0]<20:return cached[1]
    try:
        p=read(DEST/'profiles/self.json')
        d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        folder=DEST/'nodes'/lease['node'];body=read(folder/'REQUEST.json')
        assert d['UserCommand']==body['UserCommand'] and str(d['WorkspaceId'])==str(p['workspace_id'])
        assert d['JobMaxRunningTimeMinutes']>=4320
        CACHE[job]=(time.monotonic(),d);ISSUES.pop(job,None);return d
    except RuntimeError as e:
        ISSUES[job]=dict(time=stamp(),error=str(e));return cached[1] if cached else None

def age(value):
    if value.get('status')=='AUTHORIZED_CLONE':
        d=cloud(value)
        if d and d['Status'] in ['Queuing','Creating','Dequeued','WaitingConfig','Pending']:return 0.
        if d and d.get('GmtRunningTime'):
            started=dt.datetime.fromisoformat(d['GmtRunningTime'].replace('Z','+00:00'))
            return (dt.datetime.now(dt.timezone.utc)-started).total_seconds()
    return original_age(value)

def atomic(path,value):
    if path==DEST/'CLONE_LIVE_LATEST.json':
        for item in value['jobs']:
            folder=DEST/'nodes'/item['id'];activation=folder/'ADOPTED_CLONE.json'
            if not activation.exists():continue
            lease=read(activation);d=cloud(lease)
            if d is None:continue
            item['shared_runtime_status']=item['status'];item['status']=d['Status']
            item['peer_cloud_status_not_assumed']=False;item['peer_cloud_status_verified']=True
            item['allocated_fresh']=item['allocated_fresh'] and d['Status']=='Running'
            created=dt.datetime.fromisoformat(d['GmtCreateTime'].replace('Z','+00:00'))
            deadline=created+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
            item.update(conservative_deadline=deadline.isoformat(),deadline_basis='verified_actual_clone_creation_plus_maximum',
                hours_left=round((deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()/3600,3))
        value['clone_cloud_query_issues']=dict(ISSUES)
        value['running_allocated_cards']=sum(j['cards'] for j in value['jobs'] if j['allocated_fresh'])
        value['enabled_card_workers']=sum(j['cards'] for j in value['jobs'] if j['allocated_fresh'] and j['gpu_enabled'])
    original_atomic(path,value)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006');p.add_argument('--period',type=int,default=60)
    p.add_argument('--warn-minutes',type=float,default=30);p.add_argument('--once',action='store_true');a=p.parse_args();assert 1<=a.period<=60
    previous.WATCH=previous.WATCH+[DEST/'analysis_move/SERVICE_READY.json']+[
        ROOT/read(ROOT/n['config'])['folder']/name for n in read(DEST/'REGISTRY.json')['nodes'] if n['kind']=='elastic'
        for name in ['FIVE_MINUTE_PHASE_CHECK.json','GPU_QUEUE_FIVE_MINUTE_CHECK.json']]
    previous.adapter_failure_resolved=resolved;previous.age=age;previous.atomic=atomic;previous.main(a)
