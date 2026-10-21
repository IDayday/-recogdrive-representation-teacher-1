"""Contiguous causal expert/system waves, prioritizing independent-fold evidence."""
from r2_common import *
from r2_resume_support import register_once,enqueue
import re


def order(task):
    system=Path(task['responsibility_meta']).stem;match=re.search(r'_K(\d+)_seed([0-2])$',system);assert match
    K,replicate=map(int,match.groups());held=task['heldout_fold']
    return (not(held>=0 and replicate==0 and K in [2,3,4]),not(held>=0 and replicate==0),held,K,system,task['expert'],task['block'])


def main():
    setup('causal_priority_admission');path=ROOT/'config/CAUSAL_EXPERT_PROTOCOL_V1.json'
    while not path.exists():time.sleep(15)
    fits=sorted(read(path)['fit_tasks'],key=order);canonical=ROOT/'runs/causal_expert_quick_v1';base=ROOT/'runs/prioritized_causal_admission_v1'
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='contiguous_causal_expert_priority_waves',path=str(base.relative_to(ROOT)),handler='code/r2_scientific_admission.py',handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),kind='custom',priority=23.85,enabled=False))
    queue=read(base/'tasks.json');known={t['id'] for t in queue};handled=set()
    while len(handled)<len(fits):
        changed=False
        for fit in fits:
            if fit['id'] in handled:continue
            point=canonical/'points'/(fit['id']+'.json')
            if not point.exists():
                result=ROOT/'analysis/delta_experts'/(fit['id']+'.json')
                if result.exists() and not read(result).get('fits'):handled.add(fit['id']);continue
                # Preserve group-contiguous priority even while metadata catches up.
                break
            descriptor=read(point)
            for start in range(0,len(descriptor['panel']),4):
                task=dict(id=fit['id']+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(descriptor['panel'])),stage=str(canonical.relative_to(ROOT)))
                carrier=dict(id='causal_priority_'+digest(task)[:24],canonical_stage=str(canonical.relative_to(ROOT)),canonical_task=task,
                    scientific_handler=dict(handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom'))
                enqueue(queue,known,carrier)
            handled.add(fit['id']);changed=True
        if changed:atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),fit_points=len(handled),time=stamp()))
        time.sleep(30)
    atomic(base/'producer.json',dict(complete=True,tasks=len(queue),fit_points=len(handled),time=stamp()))


if __name__=='__main__':main()
