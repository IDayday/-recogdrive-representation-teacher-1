"""Quiet mechanical wait for training stage boundaries, errors or new nodes."""
from d4_common import *
import argparse


def main(a):
    suite=read(ROOT/a.suite)
    while True:
        progress=[];all_done=True
        for spec in suite['runs']:
            run=ROOT/'runs'/spec['run_id'];failed=next((run/'failures').glob('*.json'),None)
            if failed:
                print(json.dumps(dict(event='TRAINING_FAILED_REQUIRES_REVIEW',time=stamp(),run=spec['run_id'],path=str(failed))),flush=True);return
            complete=run/'TRAINING_COMPLETE.json'
            if not complete.exists():all_done=False
            early=run/'EARLY_PHASE_READY.json';ack=ROOT/'provenance/training_phase_reviews_v1'/(spec['run_id']+'.json')
            if early.exists() and not ack.exists():
                print(json.dumps(dict(event='EARLY_TRAINING_METRICS_REQUIRE_REVIEW',time=stamp(),run=spec['run_id'],path=str(early))),flush=True);return
            states=[read(p) for p in (run/'ranks').glob('rank*/LIVE.json')]
            progress.append(dict(run=spec['run_id'],complete=complete.exists(),active_ranks=len(states),
                minimum_optimizer_step=min([x.get('global_step',0) for x in states],default=0)))
        if all_done:
            print(json.dumps(dict(event='ALL_SUITE_TRAINING_COMPLETE_REQUIRES_ACCEPTANCE',time=stamp(),progress=progress)),flush=True);return
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
