"""Weighted mechanical admission to keep experiment families progressing together.

Fixed scientific handlers, canonical claims and seeds are preserved. Weights only
control supply. Running work is never preempted. Idle primary workers can still
take the existing broad sweeps while fresh dependent tasks become available.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
import re


def original_order(task):
    held=task.get('heldout_fold',-1);seed_value=task.get('fit_seed',0);K=task.get('K',99)
    return (0 if held>=0 and seed_value==2026101801 and K in [2,3,4] else 1,
            0 if held>=0 and seed_value==2026101801 else 1,
            0 if held<0 else 1,held,K,task.get('system',''),task.get('expert',-1),task.get('block',''),task['id'])


def main():
    setup('fair_admission')
    while not (ROOT/'provenance/SCIENTIFIC_ADMISSION_SMOKE_PASS.json').exists():time.sleep(15)
    config_path=ROOT/'config/FAIR_ADMISSION_PROTOCOL_V1.json';root=ROOT/'runs/fair_scientific_admission_v1';handler='code/r2_scientific_admission.py'
    generations=sorted(root.glob('g[0-9]*'));known=set();outstanding={};cache={};supplement={};cursor={};disabled=set()
    for generation in generations:
        for carrier in read(generation/'tasks.json'):
            known.add(carrier['id'])
            if not (generation/'receipts'/(carrier['id']+'.json')).exists():outstanding[carrier['id']]=(generation,carrier)
    number=int(generations[-1].name[1:]) if generations else 0
    base=root/('g%04d'%number)
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='weighted_admission_g%04d'%number,path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=18))
    queue=read(base/'tasks.json')
    while True:
        config=read(config_path);registry=read(ROOT/'config/GPU_STAGES.json');available={}
        for stage in registry['stages']:
            if stage['path'] in config['stage_groups']:
                old=available.get(stage['path'])
                if old is None or stage['priority']<old['priority']:available[stage['path']]=stage
        # Disable only direct claims for the configured scientific paths. Existing
        # in-flight tasks continue and producers retain their complete manifests.
        paths=set(available)|set(config.get('superseded_admission_paths',[]))
        pending_generations={str(g.relative_to(ROOT)) for g,_ in outstanding.values()}
        retired={s['path'] for s in registry['stages'] if s['path'].startswith('runs/fair_scientific_admission_v1/g') and s['path']!=str(base.relative_to(ROOT)) and s['path'] not in pending_generations}
        if any(s['path'] in (paths|retired) and s.get('enabled',True) for s in registry['stages']):
            with (ROOT/'config/gpu_stages.lock').open('a+') as guard:
                fcntl.flock(guard,fcntl.LOCK_EX);current=read(ROOT/'config/GPU_STAGES.json')
                for stage in current['stages']:
                    if stage['path'] in (paths|retired):stage['enabled']=False
                current['time']=stamp();atomic(ROOT/'config/GPU_STAGES.json',current)
            disabled|=paths
        cloud=read(ROOT/'resources/CLOUD_LATEST.json');nodes={n['name']:n for n in read(ROOT/'resources/NODES.json')['nodes']}
        capacity=sum(len(nodes[n['name']]['devices']) for n in cloud['nodes'] if n['status']=='Running' and (RUN/'nodes'/n['name']/'GPU_SMOKE_PASS.json').exists())
        assert capacity>0
        groups={};receipts={};claims={};specs={}
        for name,stage in available.items():
            group=config['stage_groups'][name];folder=ROOT/name;tasks_path=folder/'tasks.json'
            if not tasks_path.exists():continue
            version=tasks_path.stat().st_mtime_ns
            if cache.get(name,(None,None))[0]!=version:
                tasks=read(tasks_path)
                if name=='runs/behavior_experts_v1':tasks=sorted(tasks,key=original_order)
                cache[name]=(version,tasks);cursor[name]=0
            tasks=cache[name][1]
            # An upstream metadata producer can spend minutes constructing future
            # points. Admit already-frozen ready point files without waiting for
            # its final whole-manifest publication; IDs/geometry are unchanged.
            if name=='runs/causal_expert_quick_v1' and not tasks:
                found=supplement.setdefault(name,{})
                for p in (folder/'points').glob('*.json'):
                    if p.stem in found:continue
                    d=read(p);found[p.stem]=[dict(id=p.stem+'_%04d'%start,point=str(p.relative_to(ROOT)),start=start,end=min(start+4,len(d['panel'])),stage=name) for start in range(0,len(d['panel']),4)]
                tasks=sum(found.values(),[])
            done={p.stem for p in (folder/'receipts').glob('*.json')};owned={p.name for p in (folder/'claims').iterdir()} if (folder/'claims').exists() else set()
            receipts[name]=done;claims[name]=owned;specs[name]=stage
            entry=groups.setdefault(group,dict(pending=[],reserved=set(),weight=config['groups'][group]['weight'],prefetch=config['groups'][group]['prefetch']))
            entry['reserved'].update((name,ident) for ident in owned-done)
            index=cursor.get(name,0)
            while index<len(tasks):
                task=tasks[index];key=(name,task['id'])
                alias='admit_'+digest(dict(stage=name,id=task['id']))[:24]
                if task['id'] in done or task['id'] in owned or alias in known:index+=1;continue
                break
            cursor[name]=index
            # A compact suffix is enough to fill the next mechanical interval.
            for task in tasks[index:index+capacity*6]:
                ident=task['id'];alias='admit_'+digest(dict(stage=name,id=ident))[:24]
                if ident not in done and ident not in owned and alias not in known:entry['pending'].append((name,task,alias))
        # Include queued carriers not yet claimed, without double-counting their
        # canonical in-flight task. Completed aliases never reserve capacity.
        for ident,(generation,carrier) in list(outstanding.items()):
            if (generation/'receipts'/(ident+'.json')).exists():outstanding.pop(ident)
        for generation,carrier in outstanding.values():
            name=carrier['canonical_stage'];group=config['stage_groups'].get(name)
            if group in groups and carrier['canonical_task']['id'] not in receipts.get(name,set()):
                groups[group]['reserved'].add((name,carrier['canonical_task']['id']))
        active={k:g for k,g in groups.items() if g['pending'] or g['reserved']}
        weight=sum(g['weight'] for g in active.values());added=0
        if weight:
            for name,g in active.items():g['target']=max(1,round(capacity*g['weight']/weight));g['allowed']=g['target']*g['prefetch']
            while True:
                eligible=[(name,g) for name,g in active.items() if g['pending'] and len(g['reserved'])<g['allowed']]
                if not eligible:break
                group,g=min(eligible,key=lambda pair:len(pair[1]['reserved'])/pair[1]['target'])
                name,task,ident=g['pending'].pop(0);stage=specs[name]
                if len(queue)>=config.get('generation_tasks',4096):
                    atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=True,tasks=len(queue),time=stamp(),meaning='Metadata generation sealed; scientific work and nodes retained.'))
                    number+=1;base=root/('g%04d'%number);queue=[]
                    atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
                    register_once(dict(name='weighted_admission_g%04d'%number,path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=18))
                carrier=dict(id=ident,canonical_stage=name,canonical_task=task,scientific_handler={k:stage[k] for k in ['handler','handler_sha256','kind']},admission_group=group)
                enqueue(queue,known,carrier);outstanding[ident]=(base,carrier)
                g['reserved'].add((name,task['id']));added+=1
        if added:atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),time=stamp(),capacity=capacity))
        atomic(root/'ADMISSION_LIVE.json',dict(time=stamp(),generation=number,primary_physical_cards=capacity,added=added,outstanding_aliases=len(outstanding),groups={k:{a:v for a,v in g.items() if a not in ['pending','reserved']}|dict(reserved=len(g['reserved']),available_proposals=len(g['pending'])) for k,g in active.items()},
            scientific_tasks_unchanged=True,no_preemption=True,background_lanes_additional=True,original_queue_orders_unchanged=True))
        time.sleep(config.get('interval_seconds',10))


if __name__=='__main__':main()
