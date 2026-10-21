"""Task-scoped foreground wakeups with deadlines derived from the actual jobs."""
from common import *
import argparse,collections
from vlm_failure_resolution import acknowledged
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_event_watch import WATCH
from vlm_event_watch_v2 import errors,RUNS
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup('vlm_repair/live_watch');from cloud_api import request
    source=(ROOT/a.cloud_ready).resolve();assert source.is_relative_to(ROOT)
    cloud=read(source);assert len(cloud['jobs'])==2
    if source==ROOT/'candidate_repair_v1/CLOUD_READY.json':
        assert set(cloud['jobs'])=={'dlcmi53bf3ah2c2s','dlcms4op7agqj50d'}
    else:
        assert source.parent.is_relative_to(VOUT/'resume') and (source.parent/'PREPARED.json').exists()
    token=digest(dict(source=str(source.relative_to(ROOT)),jobs=cloud['jobs']))[:16]
    seen_path=VOUT/'live_watch'/(token+'_seen.json')
    watch=WATCH+[VOUT/'fold_backup/ALL_BACKUPS_COMPLETE.json',VOUT/'FINAL_ANALYSES_REVIEW_READY.json',SEM/'ANALYSIS_EXECUTION.json',VOUT/'late_token_coverage/SELECTION_LOCK.json',VOUT/'late_token_coverage/FITS_READY.json',VOUT/'late_token_coverage/FINAL_LOCK.json',VOUT/'late_token_coverage/INFERENCE_COMPLETE.json']
    seen=set(read(seen_path)['seen']) if seen_path.exists() else {str(p.relative_to(ROOT)) for p in watch if p.exists()}
    atomic(seen_path,dict(time=stamp(),seen=sorted(seen)))
    while True:
        try:
            bad=errors()+list((VOUT/'late_token_coverage/failures').glob('*.json'))+list((ROOT/'runs/vlm_late_qualification_20261017_v1/failures').glob('*.json'))
            if source.parent.is_relative_to(VOUT/'resume'):
                for node in [0,1]:bad += [p for p in (source.parent/f'node{node}/failures').glob('*.json') if not acknowledged(p,source.parent)] + list((source.parent/f'node{node}').glob('FAILED.json'))
            if bad:print('WAKE_AGENT_FAILURE',str(bad[0].relative_to(ROOT)),flush=True);return
            jobs=[]
            for i,job in enumerate(cloud['jobs']):
                d=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
                assert str(d['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
                if 'requests' in cloud:assert d['UserCommand']==read(ROOT/cloud['requests'][i])['UserCommand']
                created=dt.datetime.fromisoformat(d['GmtCreateTime'].replace('Z','+00:00'))
                deadline=created+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
                jobs.append(dict(job=job,status=d['Status'],deadline=deadline.isoformat(),remaining_seconds=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds(),reserved_minutes=d.get('Settings',{}).get('JobReservedMinutes'),pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]))
            if any(j['status'] in {'Succeeded','Failed','Stopped','Deleted','Terminated'} for j in jobs):
                print('WAKE_AGENT_JOB_TERMINAL',json.dumps(jobs),flush=True);return
            if min(j['remaining_seconds'] for j in jobs)<60*a.warn_minutes:
                print('WAKE_AGENT_LIFETIME',json.dumps(jobs),flush=True);return
            current={str(p.relative_to(ROOT)) for p in watch if p.exists()}
            if current-seen:
                atomic(seen_path,dict(time=stamp(),seen=sorted(seen|current)))
                print('WAKE_AGENT_PHASE',json.dumps(sorted(current-seen)),flush=True);return
            counts={}
            for run in RUNS[1:]:
                base=ROOT/'runs'/run;p=base/'tasks.json'
                counts[run]=dict(done=len(list((base/'receipts').glob('*.json'))),total=len(read(p)) if p.exists() else 0)
            value=dict(time=stamp(),jobs=jobs,counts=counts,primary_full_completed=len(list((VOUT/'scan/receipts').glob('*.json'))),semantic_full_completed=len(list((SEM/'scan/receipts').glob('*.json'))),nodes_never_stopped_or_released=True)
            atomic(VOUT/'live_watch'/(token+'_latest.json'),value)
            print(json.dumps(dict(time=value['time'],jobs=[dict(job=j['job'],status=j['status'],hours_left=round(j['remaining_seconds']/3600,2)) for j in jobs],counts=counts)),flush=True)
        except (OSError,TimeoutError) as exc:print('TRANSIENT_MONITOR_READ',type(exc).__name__,flush=True)
        if a.once:return
        time.sleep(a.period)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cloud-ready',default='candidate_repair_v1/CLOUD_READY.json');p.add_argument('--period',type=int,default=60);p.add_argument('--warn-minutes',type=float,default=20);p.add_argument('--once',action='store_true');a=p.parse_args();assert 1<=a.period<=60 and a.warn_minutes>=0;main(a)
