"""Append admitted formed packs to the compact elastic queue, without pruning.

Only already engineered packs are registered. Their train/validation stage is
unconditional; the paired frozen test waits for explicit training acceptance.
No cloud operation, release, quality screen, or new teacher snapshot occurs.
"""
from r3_common import *
import argparse
import fcntl


def main(a):
    assert (ROOT/'teachers/first42_v1/FROZEN.json').exists()
    stress=read(ROOT/'provenance/FORMED_FULL_PACK_PARALLEL_REVIEW.json')
    assert stress['status']=='PASS_FULL_PACK_48_DEVICES_FOUR_RETAINED_MODELS_EACH'
    contract=read(ROOT/'runs/stage_service_contract_v1/PASS.json')
    service=ROOT/'code/r3_stage_service_v1.py'
    assert contract['source_sha256']==sha(service)
    config=read(ROOT/'runs/formed_pack_engineering_v1/CONFIG.json')
    schedule=read(ROOT/'manifests/FORMED_SCHEDULE_DRAFT_V1.json')
    assert sha(ROOT/'manifests/FORMED_SCHEDULE_DRAFT_V1.json')==config['schedule_sha256']
    wanted=set(a.packs.split(',')) if a.packs else None
    packs=[p for p in config['packs'] if wanted is None or p['id'] in wanted]
    assert packs and (wanted is None or wanted=={p['id'] for p in packs})
    settings=[];registered=[]
    evaluator=ROOT/'code/r3_formed_rollout_v1.py'
    for pack in packs:
        audit_path=ROOT/'runs/formed_pack_engineering_v1'/pack['id']/'AUDIT.json'
        assert audit_path.exists(), 'Unengineered formed pack cannot enter the queue'
        engineering=read(audit_path);assert engineering['status']=='PASS_GENERIC_CPU_AUDIT'
        engineering_result=read(ROOT/engineering['result_path'])
        assert engineering_result['task']['pack_sha256']==pack['sha256']==sha(pack['path'])
        assert engineering_result['task']['indices']==[60,1]
        train_id=pack['id']+'_navtrain_v1';test_id=pack['id']+'_navtest_v1'
        for cohort,ident,rank in [('navtrain',train_id,0),('navtest',test_id,1)]:
            prior=ROOT/'analysis'/('first42_'+cohort+'_v1')/'SUMMARY.json'
            summary=read(prior);assert summary['status']=='PASS_COMPLETE_AUDITED_FIRST42'
            assert summary['cohort']==cohort and summary['cases']==(103288 if cohort=='navtrain' else 12146)
            stage=ROOT/'runs/formed_full_v1'/ident
            task=dict(pack=pack['path'],pack_sha256=pack['sha256'],rows=summary['rows'],rows_sha256=summary['rows_sha256'],
                seeds=[0,1,2,3,4],cohort=cohort,first42_summary=str(prior),first42_summary_sha256=sha(prior))
            requires=['teachers/first42_v1/FROZEN.json']
            if cohort=='navtest':
                lock_path=ROOT/'provenance/formed_test_locks_v1'/(pack['id']+'.json')
                if not lock_path.exists():
                    atomic(lock_path,dict(status='FROZEN_BEFORE_TEST',time=stamp(),pack_sha256=pack['sha256'],
                        test_rows_sha256=summary['rows_sha256'],seeds=[0,1,2,3,4],catalog_sha256=schedule['catalog_sha256'],
                        candidate_scope_from_preexisting_train_side_fits=True,test_feedback_used_for_expansion=False))
                lock=read(lock_path)
                assert lock['pack_sha256']==pack['sha256'] and lock['test_rows_sha256']==summary['rows_sha256']
                task.update(test_lock=str(lock_path),test_lock_sha256=sha(lock_path))
                requires.append(str((ROOT/'runs/formed_full_v1'/train_id/'AGENT_ACCEPTANCE.json').relative_to(ROOT)))
            spec=dict(case_count=summary['cases'],chunk_size=a.chunk_size,task_template=task)
            spec_path=stage/'SPECIFICATION.json'
            if spec_path.exists():assert read(spec_path)==spec
            else:atomic(spec_path,spec)
            settings.append(dict(id=ident,stage=str(stage.relative_to(ROOT)),priority=config['packs'].index(pack)*2+rank,
                handler=str(evaluator.relative_to(ROOT)),handler_sha256=sha(evaluator),specification_sha256=sha(spec_path),requires=requires))
        registered.append(dict(id=pack['id'],entries=pack['entries'],engineering_audit_sha256=sha(audit_path)))
    lock=ROOT/'runs/ELASTIC_STAGE_QUEUE.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);path=ROOT/'runs/ELASTIC_STAGE_QUEUE.json'
        queue=read(path) if path.exists() else dict(open=True,stages=[])
        existing={v['id']:v for v in queue['stages']}
        for setting in settings:
            if setting['id'] in existing:assert existing[setting['id']]==setting
            else:queue['stages'].append(setting)
        queue['time']=stamp();atomic(path,queue)
    leases=ROOT/'runs/elastic_stage_service_v1_leases'
    with (ROOT/'runs/QUEUE.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);path=ROOT/'runs/QUEUE.json';outer=read(path)
        if not (leases/'producer.json').exists():
            records=[dict(id='elastic_stage_service_v1_lease%04d'%i,stage=str(leases.relative_to(ROOT)),
                handler=str(service.relative_to(ROOT)),handler_sha256=sha(service)) for i in range(a.leases)]
            assert not {t['id'] for t in records}&{t['id'] for t in outer['tasks']}
            atomic(leases/'tasks.json',records)
            atomic(leases/'producer.json',dict(complete=True,time=stamp(),tasks=len(records),elastic=True,open_until_user_instruction=True))
            outer['tasks'].extend(records);outer['time']=stamp();atomic(path,outer)
    proof=ROOT/'provenance/formed_stage_registrations_v1'/('registration_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    atomic(proof,dict(status='REGISTERED_ENGINEERED_FORMED_FULL_STAGES',time=stamp(),packs=registered,
        added_stage_ids=[v['id'] for v in settings],all_existing_formed_candidates_full_coverage=True,
        test_requires_train_acceptance=True,source_sha256=sha(Path(__file__)),nodes_released=False))
    print(json.dumps(dict(status='REGISTERED',packs=len(packs),stages=len(settings),path=str(proof.relative_to(ROOT)))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--packs');p.add_argument('--chunk-size',type=int,default=2)
    p.add_argument('--leases',type=int,default=512);main(p.parse_args())
