"""Foreground completion/deadline wakeups for configurable registered DLC nodes."""
from common import *
import argparse
from vlm_elastic_registry import DEST,BASE
from vlm_elastic_cloud import request
from vlm_failure_resolution import acknowledged
from vlm_event_watch import WATCH
from vlm_event_watch_v2 import errors
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup('vlm_repair/elastic_watch');resume=ROOT/a.legacy_resume
    seen_path=DEST/'WATCH_SEEN.json';seen=set(read(seen_path)['seen']) if seen_path.exists() else set()
    watch=WATCH+[DEST/'DYNAMIC_ACCEPTANCE_READY.json',DEST/'FULL_SCAN_COMPLETE.json',
        DEST.parent/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json',
        DEST.parent/'late_token_coverage/SELECTION_LOCK.json',DEST.parent/'late_token_coverage/FINAL_LOCK.json',
        DEST.parent/'late_token_coverage/INFERENCE_COMPLETE.json',DEST.parent/'qda_neighbor_repair/FINAL_LOCK.json',
        DEST.parent/'qda_neighbor_repair/INFERENCE_COMPLETE.json',DEST.parent/'ALL_BATCHES_ANALYSES_REVIEW_READY.json',
        DEST.parent/'ALL_FOUR_BATCHES_ANALYSES_REVIEW_READY.json',DEST.parent/'ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY.json']
    for name in ['NO_COMPETITIVE_CANDIDATES.json','FINAL_LOCK.json','FEATURE_ENGINEERING_PASS.json',
                 'test_features/COLLECTION_COMPLETE.json','INFERENCE_COMPLETE.json']:
        watch.append(DEST.parent/'observation_qda_gate'/name)
    while True:
        bad=errors()
        for root in [DEST,DEST.parent/'late_token_coverage',DEST.parent/'qda_neighbor_repair',DEST.parent/'observation_qda_gate']:
            bad+=list((root/'failures').glob('*.json'))
        for n in read(DEST/'REGISTRY.json')['nodes']:
            if n['kind']=='elastic':bad+=list((ROOT/read(ROOT/n['config'])['folder']/'failures').glob('*.json'))
        for node in range(len(read(resume/'CLOUD_READY.json')['jobs'])):
            retirement=DEST/'retirements'/f'legacy_{node}.json'
            if retirement.exists():
                proof=read(retirement)
                assert proof['status']=='PASS' and proof['job']==read(resume/'CLOUD_READY.json')['jobs'][node]
                assert len(proof['double_terminal_checks'])==2
                continue
            bad += [p for p in (resume/f'node{node}/failures').glob('*.json') if not acknowledged(p,resume)]
            bad += list((resume/f'node{node}').glob('FAILED.json'))
        if bad:print('WAKE_AGENT_FAILURE',str(bad[0].relative_to(ROOT)),flush=True);return
        jobs=[];transient=[];node_watch=[]
        for n in read(DEST/'REGISTRY.json')['nodes']:
            if n['kind']=='legacy':
                profile=read(DEST/'profiles/self.json');job=n['job'];body=None
            else:
                c=read(ROOT/n['config']);folder=ROOT/c['folder']
                node_watch += [folder/name for name in ['PREFLIGHT.json','CPU_SMOKE_PASS.json','GPU_SMOKE_PASS.json','ENGINEERING_PASS.json','GPU_ENABLED.json']]
                if not (folder/'SUBMITTED.json').exists():continue
                profile=read(ROOT/c['profile_path']);job=read(folder/'SUBMITTED.json')['job'];body=read(folder/'REQUEST.json')
            try:
                d=request(profile,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
                assert str(d['WorkspaceId'])==str(profile['workspace_id'])
                if body is not None:
                    assert d['ResourceId']==profile['quota_id'] and d['UserCommand']==body['UserCommand']
                    assert d['JobMaxRunningTimeMinutes']>=4320,'New node lifetime below 72 hours.'
                created=dt.datetime.fromisoformat(d['GmtCreateTime'].replace('Z','+00:00'))
                deadline=created+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
                jobs.append(dict(id=n['id'],job=job,status=d['Status'],cards=n['cards'],
                    deadline=deadline.isoformat(),hours_left=round((deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()/3600,3),
                    gpu_enabled=n['kind']=='legacy' or (folder/'GPU_ENABLED.json').exists(),
                    retired=(DEST/'retirements'/(n['id']+'.json')).exists()))
            except RuntimeError as error:transient.append(dict(id=n['id'],error=str(error)))
        current={str(p.relative_to(ROOT)) for p in watch+node_watch if p.exists()}
        value=dict(time=stamp(),jobs=jobs,cloud_query_issues=transient,
            full_cells=len(list((DEST.parent/'scan/receipts').glob('*.json'))),
            global_tasks=len(read(BASE/'tasks.json')),global_done=len(list((BASE/'receipts').glob('*.json'))),
            running_allocated_cards=sum(j['cards'] for j in jobs if j['status']=='Running' and not j['retired']),
            enabled_card_workers=sum(j['cards'] for j in jobs if j['status']=='Running' and j['gpu_enabled'] and not j['retired']))
        atomic(DEST/'LIVE_LATEST.json',value)
        if any(j['status'] in ['Stopped','Failed','Succeeded','Deleted','Terminated'] and not j['retired'] for j in jobs):print('WAKE_AGENT_JOB_TERMINAL',json.dumps(value),flush=True);return
        if any(j['hours_left']<a.warn_minutes/60 and not j['retired'] for j in jobs):print('WAKE_AGENT_LIFETIME',json.dumps(value),flush=True);return
        if seen and current-seen:
            atomic(seen_path,dict(time=stamp(),seen=sorted(seen|current)))
            print('WAKE_AGENT_PHASE',json.dumps(sorted(current-seen)),flush=True);return
        seen|=current;atomic(seen_path,dict(time=stamp(),seen=sorted(seen)))
        print(json.dumps(value),flush=True)
        if a.once:return
        time.sleep(a.period)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006');p.add_argument('--period',type=int,default=60);p.add_argument('--warn-minutes',type=float,default=20);p.add_argument('--once',action='store_true');a=p.parse_args();assert 1<=a.period<=60;main(a)
