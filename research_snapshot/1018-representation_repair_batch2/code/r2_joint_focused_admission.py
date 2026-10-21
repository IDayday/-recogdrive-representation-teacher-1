"""Dense K/family/fold screening first; fitting replicas admitted for finalists.

No scientific task is changed or deleted. Full original three-seed queues remain
available. Existing replicas finish. This is reversible hierarchical scheduling,
so an expensive routing grid cannot postpone every other method until completion.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from functools import lru_cache
import re


@lru_cache(maxsize=1024)
def recipe(selection):
    d=read(ROOT/selection);match=re.match(r'(.+)_K(\d+)_seed([0-2])$',d['system']);assert match
    return dict(family=match.group(1),K=int(match.group(2)),replicate=int(match.group(3)),heldout_fold=d['heldout_fold'])


def main():
    setup('focused_joint_admission');source=ROOT/'runs/behavior_router_training_v1';base=ROOT/'runs/focused_joint_admission_v1';handler='code/r2_scientific_admission.py'
    while not (source/'tasks.json').exists():time.sleep(15)
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='hierarchical_joint_replicate_admission',path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.25,enabled=False))
    queue=read(base/'tasks.json');known={t['id'] for t in queue};version=None;tasks=[]
    while True:
        current=(source/'tasks.json').stat().st_mtime_ns
        if current!=version:tasks=read(source/'tasks.json');version=current
        config=read(ROOT/'config/JOINT_REPLICATION_ADMISSION.json');changed=False;deferred=0
        for task in tasks:
            r=recipe(task['selection']);allowed=r['replicate']==0 or config.get('admit_all_replicates',False)
            for candidate in config.get('replicate_recipes',[]):
                if all(r.get(k,task.get(k))==v for k,v in candidate.items()):allowed=True
            if not allowed:deferred+=1;continue
            ident='focused_joint_'+digest(dict(stage=str(source.relative_to(ROOT)),id=task['id']))[:24]
            if ident in known:continue
            carrier=dict(id=ident,canonical_stage=str(source.relative_to(ROOT)),canonical_task=task,
                scientific_handler=dict(handler='code/r2_behavior_router.py',handler_sha256=sha(ROOT/'code/r2_behavior_router.py'),kind='custom'))
            enqueue(queue,known,carrier);changed=True
        if changed:atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),time=stamp(),replica_tasks_deferred=deferred))
        atomic(base/'ADMISSION_LIVE.json',dict(time=stamp(),original_tasks=len(tasks),admitted=len(queue),currently_deferred=deferred,
            scientific_configurations_unchanged=True,existing_inflight_replicas_not_stopped=True,all_formal_finalists_require_replicate_confirmation=True))
        time.sleep(30)


if __name__=='__main__':main()
