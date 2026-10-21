"""Repair interrupted append commits and archive uncommitted CPU arrays after expiry.

Call before vlm_resume.py prepare. It refuses all mutations while either original
job is active; immutable completed results are never moved or rewritten.
"""
from common import *
from vlm_resume import old_status,TERMINAL,move
from vlm_core import VOUT
from vlm_quiescence import assert_quiescent
from repair_queue_v2 import append,atomic_unique as atomic

def recover_stages(base,archive):
    if not (base/'tasks.json').exists():return []
    registered=read(base/'tasks.json');done=[]
    for path in sorted((base/'stages').glob('*/PROTOCOL.json')):
        p=read(path);name=path.parent.name;current=[t for t in registered if t['stage']==name]
        assert len(current) in [0,p['tasks']],name
        if len(current)==p['tasks']:continue
        panel=read(path.parent/'panel.json');arms=read(path.parent/'arms.json')
        assert sha(path.parent/'panel.json')==p['panel_sha256'] and sha(path.parent/'arms.json')==p['arms_sha256']
        candidates={}
        for chunk in [1,2,4,8,16,32,64]:
            tasks=[dict(id=f'{name}_a{a:05d}_{i:06d}',stage=name,start=i,end=min(i+chunk,len(panel)),arm_start=a,arm_end=min(a+64,len(arms)),seeds=p['seeds']) for a in range(0,len(arms),64) for i in range(0,len(panel),chunk)]
            if len(tasks)==p['tasks']:candidates[digest(tasks)]=tasks
        assert len(candidates)==1, 'Ambiguous interrupted stage; inspect original code: '+name
        tasks=next(iter(candidates.values()));append(base,tasks);registered.extend(tasks)
        done.append(dict(stage=name,tasks=len(tasks),protocol_sha256=sha(path),reconstructed_only_original_frozen_tasks=True))
    return done

def archive_partial_cpu(root,archive):
    moved=[]
    for kind in ['scan','rapid']:
        base=root/kind
        for claim in (base/'claims').glob('*'):
            if not claim.is_dir() or (base/'receipts'/(claim.name+'.json')).exists() or (base/'results'/(claim.name+'.json')).exists():continue
            owner=read(claim/'OWNER.json') if (claim/'OWNER.json').exists() else {}
            if owner.get('status')=='SCHEDULER_RESERVED':continue
            # A preemption between npz and result.json does not commit a result.
            # Preserve it rather than demanding bit equality after a different
            # BLAS thread partition recomputes the unfinished cell.
            moment=(root/'moments' if kind=='scan' else base/'moments')/(claim.name+'.npz')
            for path in [base/'arrays'/(claim.name+'.npz'),moment]:
                if path.exists():moved.append(str(path.relative_to(ROOT)));move(path,archive)
    return moved

if __name__=='__main__':
    setup('vlm_repair/resume_stage_registry');states=assert_quiescent()[-1]["jobs"]
    dest=VOUT/'resume'/('registry_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S'));dest.mkdir(parents=True,exist_ok=False)
    commits={run:recover_stages(ROOT/'runs'/run,dest) for run in ['vlm_repair_20261016_v2','vlm_global_refine_20261016_v5']}
    partial=[]
    for root in [VOUT,ROOT/'vlm_semantic_v2']:partial+=archive_partial_cpu(root,dest/'uncommitted_cpu_arrays')
    atomic(dest/'RECOVERY.json',dict(status='PASS',time=stamp(),old_jobs=states,append_commits=commits,uncommitted_cpu_arrays_archived=partial,completed_results_untouched=True))
    print('STAGE_REGISTRY_RECOVERY_PASS',str(dest.relative_to(ROOT)),flush=True)
