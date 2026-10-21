"""Response libraries for feedback-refitted experts, kept outside round-zero EM."""
from r2_common import *
from r2_resume_support import append_once,register_once,enqueue
from r2_coarse_producer import balanced
from collections import defaultdict


def main():
    setup('variant_library_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);queued=set();handled=set();panels={}
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    stages=[ROOT/'runs/variant_library_S0_v1',ROOT/'runs/variant_library_noise_v1'];queues={};known={}
    for base,priority in zip(stages,[23.1,23.6]):
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        queues[base]=read(base/'tasks.json');known[base]={t['id'] for t in queues[base]}
        register_once(dict(name=base.name,path=str(base.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=priority))
    while True:
        tasks=[];train=ROOT/'runs/em_behavior_experts_v1/tasks.json';models=defaultdict(list)
        if train.exists():
            for task in read(train):models[(task['responsibility_meta'],task['system'],task['heldout_fold'])].append(task)
        changed=False
        for key,entries in models.items():
            meta_path,system,held=key;ident='variant_library_'+digest(dict(meta=meta_path,system=system,held=held))[:24]
            if ident not in queued:
                meta=read(ROOT/meta_path);active=[e for e in range(meta['K']) if meta['effective_counts'][e]>=24 and meta['sessions'][e]>=4]
                expected=0;ready=True
                for e in active:
                    for site in ['interface_pre','interface_post']:
                        spaces=[]
                        for centered in [False,True]:
                            # Space IDs are deterministic from the exact original
                            # task spec, avoiding repeated huge directory scans.
                            cell=cells[site+'__valid_mean']
                            spec=dict(cell=cell,expert=e,heldout_fold=held,centered=centered,responsibility_meta=meta_path)
                            path=ROOT/'analysis/expert_spaces'/('space_learned_em1_'+digest(spec)[:24]+'.json')
                            if not path.exists():ready=False;break
                            spaces.append(read(path))
                        if not ready:break
                        quality_fits=[f for d in spaces for f in d.get('fits',[]) if f['config']['kind'] in ['basis_residual','variance_residual'] and 8<=f['r']<=256]
                        expected+=1+bool(quality_fits)
                    if not ready:break
                responses=[ROOT/'analysis/responses/em_behavior_quick_v1'/(m['id']+'.json') for m in entries]
                if ready and len(entries)==expected and all(p.exists() for p in responses):
                    tasks.append(dict(id=ident,handler='code/r2_variant_bank.py',handler_sha256=sha(ROOT/'code/r2_variant_bank.py'),responsibility_meta=meta_path,system=system,responses=[str(p.relative_to(ROOT)) for p in responses]));queued.add(ident)
            selection_path=ROOT/'analysis/variant_library_selection'/(ident+'.json')
            if ident in handled or not selection_path.exists():continue
            selection=read(selection_path)
            if held not in panels:
                mask=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows]);salt=dict(variant_library_panel=20261018,held=held)
                f=np.flatnonzero(mask&(quality<.7)).tolist();h=balanced(np.flatnonzero(mask&(quality>.9)),rows,256,salt);m=balanced(np.flatnonzero(mask&(quality>=.7)&(quality<=.9)),rows,128,salt)
                parts0=dict(failure=f,high=h,intermediate=m);parts1=dict(failure=balanced(f,rows,256,salt),high=h[:128],intermediate=m[:64]);panels[held]=[(sum(parts0.values(),[]),parts0),(sum(parts1.values(),[]),parts1)]
            for n,base,seeds in [(0,stages[0],[0]),(1,stages[1],[1,2])]:
                panel,partitions=panels[held][n];point=base/'points'/(ident+'.json')
                if not point.exists():atomic(point,dict(id=ident,system=system,K=selection['K'],heldout_fold=held,arms=selection['arms'],policies=selection['policies'],selection=str(selection_path.relative_to(ROOT)),panel=panel,panel_partitions=partitions,seeds=seeds,training_only=True,formation_round=1))
                for start in range(0,len(panel),8):enqueue(queues[base],known[base],dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+8,len(panel)),stage=str(base.relative_to(ROOT))))
            handled.add(ident);changed=True
        if tasks:append_once('cpu',tasks)
        if changed:
            for base,queue in queues.items():atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),systems=len(handled),time=stamp()))
        time.sleep(60)


if __name__=='__main__':main()
