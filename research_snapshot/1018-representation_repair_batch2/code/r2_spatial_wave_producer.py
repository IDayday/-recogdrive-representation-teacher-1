"""Prioritize functional all-component probes without recollecting representations."""
from r2_common import *
from r2_resume_support import register_once,enqueue


def main():
    setup('spatial_wave_producer');manifest=ROOT/'config/SPATIAL_DISCOVERY_WAVE1.json'
    while not manifest.exists():time.sleep(15)
    entries=read(manifest)['entries'];wave=ROOT/'runs/spatial_wave_admission_v1';private=ROOT/'runs/spatial_discovery_global_v1'
    for base in [wave,private]:
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='spatial_component_functional_discovery',path=str(wave.relative_to(ROOT)),handler='code/r2_scientific_admission.py',handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),kind='custom',priority=28,enabled=False))
    queue=read(wave/'tasks.json');known={t['id'] for t in queue};private_queue=read(private/'tasks.json');private_known={t['id'] for t in private_queue};handled=set();skipped=[]
    while True:
        config=read(ROOT/'config/SPATIAL_REPLICATION_ADMISSION.json');changed=False;private_changed=False
        for entry in entries:
            if entry['id'] in handled:continue
            allowed=entry['fit_seed']==2026101801 or config.get('admit_all_replicates',False)
            for r in config.get('replicate_recipes',[]):
                if all(entry.get(k)==v for k,v in r.items()):allowed=True
            if not allowed:continue
            fit_result=ROOT/'analysis/expert_spaces'/(entry['id']+'.json')
            if fit_result.exists() and read(fit_result)['status']!='PASS':skipped.append(dict(id=entry['id'],reason=read(fit_result)['status']));handled.add(entry['id']);continue
            if entry['global_repr']:
                source=ROOT/'runs/representation_coarse_v1/points'/(entry['id']+'.json')
                if not source.exists():continue
                original=read(source);point=private/'points'/(entry['id']+'.json')
                if not point.exists():
                    parity=int(digest(dict(task=entry['id'],allocation=20261018))[:8],16);types=['success_pca' if parity%2==0 else 'failure_pca','basis_residual' if parity%4<2 else 'variance_residual'];selected=[]
                    for j,kind in enumerate(types):
                        options=[f for f in original['fit_metadata'] if f['config']['kind']==kind]
                        if options:selected.append(sorted(options,key=lambda f:f['r'],reverse=bool((parity+j)%2))[0])
                    if not selected:selected=original['fit_metadata'][:1]
                    fits={f['path'] for f in selected};arms=[a for a in original['arms'] if a['fit_path'] in fits and ((a['alpha']==1. and a['cap']==.02) or (a['method'] in ['mean','ot','quality'] and (a['alpha'],a['cap']) in [(.25,.005),(1.,.1)]))]
                    p=original['panel_partitions'];parts=dict(own=p['own'][:3],other=p['other'][:2],success=p['success'][:2],intermediate=p['intermediate'][:1]);panel=sum(parts.values(),[]);assert len(panel)==len(set(panel))==8
                    atomic(point,dict(id=entry['id'],task=original['task'],fit_metadata=selected,all_fit_metadata=original['fit_metadata'],arms=arms,panel=panel,panel_partitions=parts,seeds=[0],training_only=True,actual_outcome_cv=False,
                        source_original=str(source.relative_to(ROOT)),source_original_sha256=sha(source),purpose='Balanced small functional wave; complete original broad sweep remains intact.'))
                base=private;descriptor=read(point)
                for start in range(0,len(descriptor['panel']),2):enqueue(private_queue,private_known,dict(id=entry['id']+'_%02d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+2,len(descriptor['panel']))))
                private_changed=True
            else:
                base=ROOT/'runs/fold_and_outcome_probes_v1';point=base/'points'/(entry['id']+'.json')
                if not point.exists():continue
                descriptor=read(point)
            for start in range(0,len(descriptor['panel']),2):
                canonical=dict(id=entry['id']+'_%02d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+2,len(descriptor['panel'])))
                carrier=dict(id='spatial_wave_'+digest(dict(stage=str(base.relative_to(ROOT)),id=canonical['id']))[:24],canonical_stage=str(base.relative_to(ROOT)),canonical_task=canonical,
                    scientific_handler=dict(handler='code/r2_eval_rollouts.py',handler_sha256=sha(ROOT/'code/r2_eval_rollouts.py'),kind='rollouts'))
                enqueue(queue,known,carrier)
            handled.add(entry['id']);changed=True
        if private_changed:atomic(private/'tasks.json',private_queue);atomic(private/'producer.json',dict(complete=False,tasks=len(private_queue),time=stamp()))
        if changed:atomic(wave/'tasks.json',queue);atomic(wave/'producer.json',dict(complete=False,tasks=len(queue),points=len(handled),skipped=skipped,time=stamp()))
        atomic(ROOT/'analysis/spatial_discovery/PRODUCER.json',dict(time=stamp(),entries=len(entries),admitted_points=len(handled),carrier_tasks=len(queue),skipped=skipped))
        time.sleep(30)


if __name__=='__main__':main()
