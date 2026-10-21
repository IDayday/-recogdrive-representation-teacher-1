"""Cloud-verified event monitor acknowledging the overdue running legacy job."""
from vlm_clone_watch import *
import vlm_clone_watch_v3 as cloud_watch
from vlm_clone_watch_v2 import resolved
from vlm_clone_watch_v4 import EventsOnly
import contextlib
age=cloud_watch.age
atomic=cloud_watch.atomic
adapter_failure_resolved=resolved
def main(a):
    setup('vlm_repair/clone_watch');resume=ROOT/a.legacy_resume
    seen_path=DEST/'CLONE_WATCH_SEEN.json';seen=set(read(seen_path)['seen']) if seen_path.exists() else set()
    watch=WATCH+[DEST/'DYNAMIC_ACCEPTANCE_READY.json',DEST/'FULL_SCAN_COMPLETE.json',
        DEST.parent/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json',DEST.parent/'final/PRIMARY_STAGES_APPENDED.json',
        DEST.parent/'late_token_coverage/SELECTION_LOCK.json',DEST.parent/'late_token_coverage/FINAL_LOCK.json',
        DEST.parent/'late_token_coverage/INFERENCE_COMPLETE.json',DEST.parent/'qda_neighbor_repair/FINAL_LOCK.json',
        DEST.parent/'qda_neighbor_repair/INFERENCE_COMPLETE.json',DEST.parent/'ALL_BATCHES_ANALYSES_REVIEW_READY.json',
        DEST.parent/'ALL_FOUR_BATCHES_ANALYSES_REVIEW_READY.json',DEST.parent/'ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY.json']
    watch += [DEST.parent/'observation_qda_gate'/name for name in ['NO_COMPETITIVE_CANDIDATES.json',
        'FINAL_LOCK.json','FEATURE_ENGINEERING_PASS.json','test_features/COLLECTION_COMPLETE.json','INFERENCE_COMPLETE.json']]
    while True:
        try:
            bad=errors();jobs=[];issues=[];node_watch=[];alerts=[]
            for root in [DEST,DEST.parent/'late_token_coverage',DEST.parent/'qda_neighbor_repair',DEST.parent/'observation_qda_gate']:
                bad+=list((root/'failures').glob('*.json'))
            for index,job in enumerate(read(resume/'CLOUD_READY.json')['jobs']):
                retired=DEST/'retirements'/f'legacy_{index}.json'
                if retired.exists():
                    proof=read(retired);assert proof['status']=='PASS' and proof['job']==job and len(proof['double_terminal_checks'])==2
                else:
                    bad += [p for p in (resume/f'node{index}/failures').glob('*.json') if not acknowledged(p,resume)]
                    bad += list((resume/f'node{index}').glob('FAILED.json'))
            for n in read(DEST/'REGISTRY.json')['nodes']:
                retired=(DEST/'retirements'/(n['id']+'.json')).exists()
                if retired:continue
                if n['kind']=='elastic':
                    c=read(ROOT/n['config']);folder=ROOT/c['folder']
                    for sub in ['failures','clone_wrapper_failures','command_failures']:bad+=list((folder/sub).glob('*.json'))
                    node_watch += [folder/name for name in ['ADOPTED_CLONE.json','PREFLIGHT.json','CPU_SMOKE_PASS.json',
                        'GPU_SMOKE_PASS.json','ENGINEERING_PASS.json','GPU_ENABLED.json','TEMPLATE_CANCELLED.json']]
                    if (folder/'ADOPTED_CLONE.json').exists():
                        lease=read(folder/'ADOPTED_CLONE.json');assert lease['confirmed_max_minutes']>=4320
                        job=lease['job'];attest=folder/'attestations'/job
                        node_watch += [attest/'IDENTITY.json',attest/'CORE_LAUNCHED.json']
                        live=read(attest/'LIVE.json') if (attest/'LIVE.json').exists() else None
                        assert live is None or live['job']==job
                        state='AWAITING_CONTAINER' if live is None else live['status']
                        if live is None and age(lease)>600:alerts.append(dict(node=n['id'],reason='No clone heartbeat after adoption'))
                        if live is not None and age(live)>180:alerts.append(dict(node=n['id'],reason='Clone heartbeat stale',seconds=age(live)))
                        if live is not None and live['status']=='CORE_EXITED_CONTAINER_RETAINED':alerts.append(dict(node=n['id'],reason='Node core exited'))
                        if (folder/'LAUNCHED.json').exists():
                            s=read(folder/'STATUS.json') if (folder/'STATUS.json').exists() else None
                            if s is not None and age(s)>180:alerts.append(dict(node=n['id'],reason='Node supervisor heartbeat stale',seconds=age(s)))
                        # A clone is created after its source. The source creation
                        # plus confirmed clone lifetime gives an earlier, safe alarm.
                        deadline=dt.datetime.fromisoformat(read(folder/'CLOUD_STATUS.json')['deadline'])
                        jobs.append(dict(id=n['id'],job=job,status=state,cards=c['cards'],
                            gpu_enabled=(folder/'GPU_ENABLED.json').exists(),
                            allocated_fresh=live is not None and age(live)<180 and live['authorized_clone_identity'],
                            conservative_deadline=deadline.isoformat(),deadline_basis='source_creation_plus_confirmed_clone_lifetime',
                            hours_left=round((deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()/3600,3),
                            peer_cloud_status_not_assumed=True))
                        continue
                    if not (folder/'SUBMITTED.json').exists():continue
                    profile=read(ROOT/c['profile_path']);job=read(folder/'SUBMITTED.json')['job'];body=read(folder/'REQUEST.json')
                else:
                    profile=read(DEST/'profiles/self.json');job=n['job'];body=None
                try:
                    d=request(profile,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
                    assert str(d['WorkspaceId'])==str(profile['workspace_id'])
                    if body is not None:
                        assert d['ResourceId']==profile['quota_id'] and d['UserCommand']==body['UserCommand']
                        assert d['JobMaxRunningTimeMinutes']>=4320
                    created=dt.datetime.fromisoformat(d['GmtCreateTime'].replace('Z','+00:00'))
                    deadline=created+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
                    jobs.append(dict(id=n['id'],job=job,status=d['Status'],cards=n['cards'],
                        allocated_fresh=d['Status']=='Running',gpu_enabled=n['kind']=='legacy',
                        conservative_deadline=deadline.isoformat(),hours_left=round((deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()/3600,3)))
                except RuntimeError as error:issues.append(dict(id=n['id'],error=str(error)))
            current={str(p.relative_to(ROOT)) for p in watch+node_watch if p.exists()}
            value=dict(time=stamp(),jobs=jobs,cloud_query_issues=issues,alerts=alerts,
                full_cells=len(list((DEST.parent/'scan/receipts').glob('*.json'))),
                global_tasks=len(read(BASE/'tasks.json')),global_done=len(list((BASE/'receipts').glob('*.json'))),
                running_allocated_cards=sum(j['cards'] for j in jobs if j['allocated_fresh']),
                enabled_card_workers=sum(j['cards'] for j in jobs if j['allocated_fresh'] and j['gpu_enabled']))
            atomic(DEST/'CLONE_LIVE_LATEST.json',value)
            bad=[p for p in bad if not adapter_failure_resolved(p)]
            if bad:print('WAKE_AGENT_FAILURE',str(bad[0].relative_to(ROOT)),flush=True);return
            if alerts:print('WAKE_AGENT_CLONE_HEARTBEAT',json.dumps(alerts),flush=True);return
            if any(j['status'] in ['Stopped','Failed','Succeeded','Deleted','Terminated'] for j in jobs):print('WAKE_AGENT_JOB_TERMINAL',json.dumps(value),flush=True);return
            if any(j['hours_left']<a.warn_minutes/60 and not (j['id']=='legacy_1' and j['status']=='Running' and j['hours_left']<0) for j in jobs):print('WAKE_AGENT_LIFETIME',json.dumps(value),flush=True);return
            new=current-seen;atomic(seen_path,dict(time=stamp(),seen=sorted(seen|current)))
            if seen and new:print('WAKE_AGENT_PHASE',json.dumps(sorted(new)),flush=True);return
            seen|=current;print(json.dumps(value),flush=True)
            if a.once:return
        except (OSError,TimeoutError) as error:print('TRANSIENT_MONITOR_READ',type(error).__name__,flush=True)
        time.sleep(a.period)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006')
    p.add_argument('--period',type=int,default=300);p.add_argument('--warn-minutes',type=float,default=30);p.add_argument('--once',action='store_true');a=p.parse_args()
    assert 60<=a.period<=600
    WATCH=WATCH+[DEST/'analysis_move/SERVICE_READY.json']+[
        ROOT/read(ROOT/n['config'])['folder']/name for n in read(DEST/'REGISTRY.json')['nodes'] if n['kind']=='elastic'
        for name in ['FIVE_MINUTE_PHASE_CHECK.json','GPU_QUEUE_FIVE_MINUTE_CHECK.json']]
    with contextlib.redirect_stdout(EventsOnly(sys.stdout)):main(a)
