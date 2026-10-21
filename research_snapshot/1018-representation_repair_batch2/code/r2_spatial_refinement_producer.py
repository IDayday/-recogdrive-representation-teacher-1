"""Actual broad-location experts and full common-panel feedback, streamed by group."""
from r2_common import *
from r2_resume_support import append_once,register_once,enqueue
from collections import defaultdict


def main():
    setup('spatial_refinement_producer')
    paths=[ROOT/'config/SPATIAL_DISCOVERY_WAVE1.json',ROOT/'config/SPATIAL_DISCOVERY_WAVE1_UNCENTERED.json']
    while not all(p.exists() for p in paths):time.sleep(15)
    grouped=defaultdict(list)
    for path in paths:
        for entry in read(path)['entries']:grouped[(entry['heldout_fold'],entry['system'],entry['expert'])].append(entry)
    stages=[ROOT/'runs/spatial_refinement_v1',ROOT/'runs/spatial_library_S0_v1',ROOT/'runs/spatial_library_noise_v1'];queues={};known={}
    for base,priority in zip(stages,[23.9,23.2,23.68]):
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        queues[base]=read(base/'tasks.json');known[base]={t['id'] for t in queues[base]}
        register_once(dict(name=base.name,path=str(base.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=priority,enabled=False))
    proposed=set();published=set();bank_queued=set();banked=set();panels={}
    while True:
        admission=read(ROOT/'config/SPATIAL_REPLICATION_ADMISSION.json');cpu=[];changed=set();by_system=defaultdict(list)
        for (held,system,expert),entries in grouped.items():
            allowed=entries[0]['fit_seed']==2026101801 or admission.get('admit_all_replicates',False)
            for candidate in admission.get('replicate_recipes',[]):
                if all(entries[0].get(k)==v for k,v in candidate.items()):allowed=True
            if not allowed:continue
            ident='outcome_spatial_proposal_'+digest(dict(held=held,system=system,expert=expert))[:24];by_system[(held,system)].append(ident)
            if ident not in proposed:
                responses=[];ready=True
                for entry in entries:
                    result=ROOT/'analysis/expert_spaces'/(entry['id']+'.json')
                    if result.exists() and read(result)['status']!='PASS':continue
                    path=ROOT/'analysis/responses'/entry['response_stage']/(entry['id']+'.json')
                    if not path.exists():ready=False;break
                    responses.append(dict(path=str(path.relative_to(ROOT)),area=entry['area']))
                if ready and responses:
                    cpu.append(dict(id=ident,handler='code/r2_spatial_proposals.py',handler_sha256=sha(ROOT/'code/r2_spatial_proposals.py'),responsibility_meta=entries[0]['task']['responsibility_meta'],expert=expert,heldout_fold=held,system=system,responses=responses));proposed.add(ident)
                elif ready:
                    atomic(ROOT/'analysis/spatial_proposals/ineligible'/(ident+'.json'),dict(time=stamp(),system=system,heldout_fold=held,expert=expert,reason='No eligible component space'));proposed.add(ident)
            output=ROOT/'analysis/spatial_proposals'/(ident+'.json')
            if ident in published or not output.exists():continue
            point=read(ROOT/read(output)['point'])
            for start in range(0,len(point['panel']),4):enqueue(queues[stages[0]],known[stages[0]],dict(id=ident+'_%04d'%start,point=read(output)['point'],start=start,end=min(start+4,len(point['panel'])),stage=str(stages[0].relative_to(ROOT))))
            published.add(ident);changed.add(stages[0])
        for (held,system),experts in by_system.items():
            ident='spatial_library_'+digest(dict(held=held,system=system))[:24]
            if ident not in bank_queued:
                active=[e for e in experts if not (ROOT/'analysis/spatial_proposals/ineligible'/(e+'.json')).exists()]
                responses=[ROOT/'analysis/responses/spatial_refinement_v1'/(e+'.json') for e in active]
                if active and all(p.exists() for p in responses):
                    first=read(ROOT/read(ROOT/'analysis/spatial_proposals'/(active[0]+'.json'))['point'])
                    cpu.append(dict(id=ident,handler='code/r2_spatial_bank.py',handler_sha256=sha(ROOT/'code/r2_spatial_bank.py'),system=system.replace('_K','_spatial_K',1),responsibility_meta=first['task']['responsibility_meta'],responses=[str(p.relative_to(ROOT)) for p in responses]));bank_queued.add(ident)
            selection_path=ROOT/'analysis/spatial_library_selection'/(ident+'.json')
            if ident in banked or not selection_path.exists():continue
            selection=read(selection_path)
            if held not in panels:
                match=None
                for p in (ROOT/'runs/expert_library_S0_v1/points').glob('*.json'):
                    d=read(p)
                    if d['heldout_fold']==held:match=d;break
                if match is None:continue
                noise=read(ROOT/'runs/expert_library_noise_v1/points'/(match['id']+'.json'));panels[held]=[(match['panel'],match['panel_partitions']),(noise['panel'],noise['panel_partitions'])]
            for n,base,seeds in [(0,stages[1],[0]),(1,stages[2],[1,2])]:
                panel,parts=panels[held][n];point=base/'points'/(ident+'.json')
                if not point.exists():atomic(point,dict(id=ident,system=selection['system'],K=selection['K'],heldout_fold=held,arms=selection['arms'],policies=selection['policies'],selection=str(selection_path.relative_to(ROOT)),panel=panel,panel_partitions=parts,seeds=seeds,training_only=True))
                for start in range(0,len(panel),8):enqueue(queues[base],known[base],dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+8,len(panel)),stage=str(base.relative_to(ROOT))))
                changed.add(base)
            banked.add(ident)
        if cpu:append_once('cpu',cpu)
        for base in changed:atomic(base/'tasks.json',queues[base]);atomic(base/'producer.json',dict(complete=False,tasks=len(queues[base]),time=stamp()))
        atomic(ROOT/'analysis/spatial_refinement/PRODUCER.json',dict(time=stamp(),proposals=len(proposed),refinement_points=len(published),banks_queued=len(bank_queued),full_banks=len(banked)))
        time.sleep(60)


if __name__=='__main__':main()
