"""Quiet mechanical wait for training stage boundaries, errors or new nodes."""
from d4_common import *
import argparse


def main(a):
    suite=read(ROOT/a.suite)
    while True:
        priority_failure=next((B3/'runs/priority_multiplexer_v1_leases/failures').glob('*.json'),None)
        if priority_failure:
            print(json.dumps(dict(event='PRIORITY_RESOURCE_MULTIPLEXER_FAILED',time=stamp(),path=str(priority_failure))),flush=True);return
        auxiliary=ROOT/'resources/AUXILIARY_WATCHES.json'
        if auxiliary.exists():
            for watch in read(auxiliary)['watches']:
                if (ROOT/watch['acknowledgement']).exists():continue
                for label in ['failure','success']:
                    if watch.get(label) and (ROOT/watch[label]).exists():
                        print(json.dumps(dict(event='AUXILIARY_'+label.upper()+'_REQUIRES_REVIEW',time=stamp(),watch=watch['id'],path=watch[label])),flush=True);return
        evaluation=ROOT/'runs/EVALUATION_QUEUE.json'
        eval_stages=read(evaluation)['stages'] if evaluation.exists() else []
        for setting in sorted(eval_stages,key=lambda x:(x['priority'],x['id'])):
            stage=ROOT/setting['stage']
            if (stage/'AGENT_ACCEPTANCE.json').exists():continue
            for failure_dir in ['failures','audit/failures']:
                failure=next((stage/failure_dir).glob('*.json'),None)
                if failure:
                    print(json.dumps(dict(event='STUDENT_EVALUATION_FAILED',time=stamp(),stage=setting['id'],path=str(failure))),flush=True);return
            if setting['kind']=='engineering':
                if (stage/'ALL_LANES_READY.json').exists():
                    print(json.dumps(dict(event='STUDENT_EVALUATION_LANES_READY',time=stamp(),group=setting['group'],stage=setting['stage'])),flush=True);return
                continue
            if (stage/'AUDIT_COMPLETE.json').exists():
                print(json.dumps(dict(event='STUDENT_EVALUATION_STAGE_AUDITED',time=stamp(),group=setting['group'],stage=setting['stage'])),flush=True);return
            first=stage/'claims'/(setting['id']+'_000000')/'OWNER.json'
            review=ROOT/'provenance/evaluation_phase_reviews_v1'/(setting['id']+'.json')
            if first.exists() and not review.exists():
                elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(read(first)['time'])).total_seconds()
                if elapsed>=420:
                    print(json.dumps(dict(event='STUDENT_EVALUATION_EARLY_PHASE_REVIEW',time=stamp(),group=setting['group'],stage=setting['stage'])),flush=True);return
        registry=read(B3/'resources/REGISTRY.json')
        allocated={n['job'] for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes']}
        for node in registry['nodes']:
            folder=B3/'resources/nodes'/node['name']
            if not (folder/'THIRD_BATCH_GPU_ACCEPTED.json').exists():
                proofs=[B3/'runs/resident_engineering_v1'/node['name']/('device%02d'%d) for d in node['devices']]
                failure=next((p/'FAILED.json' for p in proofs if (p/'FAILED.json').exists()),None)
                if failure:
                    print(json.dumps(dict(event='NEW_NODE_MODEL_ENGINEERING_FAILED',time=stamp(),node=node['name'],path=str(failure))),flush=True);return
                if all((p/'PASS.json').exists() for p in proofs):
                    print(json.dumps(dict(event='NEW_NODE_MODEL_ENGINEERING_READY',time=stamp(),node=node['name'],devices=node['devices'])),flush=True);return
                admission=folder/'COMPATIBILITY_ADMISSION.json'
                if admission.exists() and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(read(admission)['time'])).total_seconds()>900:
                    print(json.dumps(dict(event='NEW_NODE_MODEL_ADMISSION_STALE',time=stamp(),node=node['name'])),flush=True);return
            elif node['job'] not in allocated and not (folder/'SCIENTIFIC_PHASE_ACCEPTANCE_V1.json').exists():
                elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(read(folder/'THIRD_BATCH_GPU_ACCEPTED.json')['time'])).total_seconds()
                if elapsed>=420:
                    print(json.dumps(dict(event='NEW_NODE_ORIGINAL_SCIENCE_EARLY_REVIEW',time=stamp(),node=node['name'],elapsed_seconds=elapsed)),flush=True);return
        extra=B3/'resources/EXTRA_NODE_GROUPS_V1.json'
        if extra.exists():
            for setting in read(extra)['groups']:
                if (B3/setting['review']).exists():continue
                group=read(B3/setting['manifest']);selected=[w for w in group['workers'] if w['node']==setting['node']]
                folders=[B3/'runs/extra_engineering_v1'/w['worker'] for w in selected]
                failed=next((f/'FAILED.json' for f in folders if (f/'FAILED.json').exists()),None)
                if failed:
                    print(json.dumps(dict(event='NEW_NODE_EXTRA_LANE_FAILED',time=stamp(),node=setting['node'],path=str(failed))),flush=True);return
                if selected and all((f/'PASS.json').exists() for f in folders):
                    print(json.dumps(dict(event='NEW_NODE_EXTRA_LANES_READY',time=stamp(),node=setting['node'],manifest=setting['manifest'],review=setting['review'])),flush=True);return
        original_queue=B3/'runs/ELASTIC_STAGE_QUEUE.json'
        if original_queue.exists():
            for setting in read(original_queue)['stages']:
                stage=B3/setting['stage']
                if (stage/'AGENT_ACCEPTANCE.json').exists():continue
                for name in ['failures','audit_v1/failures']:
                    failure=next((stage/name).glob('*.json'),None)
                    if failure:
                        print(json.dumps(dict(event='ORIGINAL_BATCH3_STAGE_FAILED',time=stamp(),stage=setting['stage'],path=str(failure))),flush=True);return
                if (stage/'AUDIT_COMPLETE.json').exists():
                    print(json.dumps(dict(event='ORIGINAL_BATCH3_STAGE_AUDITED',time=stamp(),stage=setting['stage'])),flush=True);return
        for launch in (ROOT/'runs/evaluation_auditor_launches_v1').glob('*.json'):
            launched=read(launch);node=launched['node'];heartbeat=ROOT/'runs/evaluation_audit_workers'/(node+'.json')
            timestamp=read(heartbeat)['time'] if heartbeat.exists() else launched['time']
            elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(timestamp)).total_seconds()
            if elapsed>900:
                print(json.dumps(dict(event='STUDENT_CPU_AUDITOR_HEARTBEAT_STALE',time=stamp(),node=node,elapsed_seconds=elapsed)),flush=True);return
        progress=[];all_done=True;all_paused=True
        for spec in suite['runs']:
            run=ROOT/'runs'/spec['run_id'];failed=next((run/'failures').glob('*.json'),None)
            if failed:
                print(json.dumps(dict(event='TRAINING_FAILED_REQUIRES_REVIEW',time=stamp(),run=spec['run_id'],path=str(failed))),flush=True);return
            complete=run/'TRAINING_COMPLETE.json'
            if not complete.exists():all_done=False
            elif not (run/'TRAINING_AGENT_ACCEPTANCE.json').exists():
                print(json.dumps(dict(event='GROUP_TRAINING_COMPLETE_REQUIRES_ACCEPTANCE',time=stamp(),run=spec['run_id'],group=spec['group'],path=str(complete))),flush=True);return
            if not (run/'ENGINEERING_BOUNDARY_PAUSE.json').exists() or (run/'RESUME_LAUNCH.json').exists():all_paused=False
            early=run/'EARLY_PHASE_READY.json';ack=ROOT/'provenance/training_phase_reviews_v1'/(spec['run_id']+'.json')
            if early.exists() and not ack.exists():
                print(json.dumps(dict(event='EARLY_TRAINING_METRICS_REQUIRE_REVIEW',time=stamp(),run=spec['run_id'],path=str(early))),flush=True);return
            for summary_path in sorted((run/'development').glob('epoch*/SUMMARY.json')):
                review=ROOT/'provenance/training_epoch_reviews_v1'/(spec['run_id']+'_'+summary_path.parent.name+'.json')
                if not review.exists():
                    print(json.dumps(dict(event='EPOCH_DEVELOPMENT_METRICS_REQUIRE_REVIEW',time=stamp(),run=spec['run_id'],path=str(summary_path))),flush=True);return
            states=[read(p) for p in (run/'ranks').glob('rank*/LIVE.json')]
            if (run/'LAUNCH.json').exists() and not complete.exists() and (not (run/'ENGINEERING_BOUNDARY_PAUSE.json').exists() or (run/'RESUME_LAUNCH.json').exists()):
                launch=read(run/'LAUNCH.json');elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(launch['time'])).total_seconds()
                stale=[v for v in states if (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(v['time'])).total_seconds()>1200]
                if (not states and elapsed>900) or stale:
                    print(json.dumps(dict(event='TRAINING_PROGRESS_STALE_REQUIRES_REVIEW',time=stamp(),run=spec['run_id'],elapsed_seconds=elapsed)),flush=True);return
            progress.append(dict(run=spec['run_id'],complete=complete.exists(),active_ranks=len(states),
                minimum_optimizer_step=min([x.get('global_step',0) for x in states],default=0)))
        if all_paused:
            print(json.dumps(dict(event='ALL_ENGINEERING_RUNS_PAUSED_FOR_RESUMPTION',time=stamp(),progress=progress)),flush=True);return
        if all_done and eval_stages and all((ROOT/v['stage']/'AGENT_ACCEPTANCE.json').exists() for v in eval_stages):
            print(json.dumps(dict(event='ALL_CURRENT_STUDENT_EVALUATIONS_ACCEPTED_REQUIRES_FINAL_REVIEW',time=stamp(),progress=progress)),flush=True);return
        cloud=read(B2/'resources/CLOUD_LATEST.json');registry=read(B3/'resources/REGISTRY.json')
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cloud['time'])).total_seconds();known={n['job'] for n in registry['nodes']}
        changed=[n for n in cloud['nodes'] if n['job'] in known and (n['status']!='Running' or n.get('remaining_seconds',999999)<7200)]
        new=[n for n in cloud['nodes'] if n['job'] in registry.get('pending_jobs',[]) and n['status']=='Running']
        if age>600 or new or changed:
            print(json.dumps(dict(event='NODE_EVENT_REQUIRES_REVIEW',time=stamp(),age_seconds=age,new=new,changed=changed)),flush=True);return
        atomic(ROOT/'runs/TRAINING_MONITOR.json',dict(status='RUNNING',time=stamp(),suite=a.suite,progress=progress,interval_seconds=a.interval))
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--suite',required=True);p.add_argument('--interval',type=int,default=60);main(p.parse_args())
