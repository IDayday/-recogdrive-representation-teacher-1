"""Bounded selected-recipe pipeline supply, retaining the original broad search.

Only ready existing canonical tasks are admitted. Targets are explicit provisional
replications; no outcomes or scientific parameters are modified by this feeder.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from functools import lru_cache


@lru_cache(maxsize=8192)
def descriptor(path):return read(ROOT/path)


def identity(t):
    while 'canonical_task' in t:t=t['canonical_task']
    if 'selection' in t:d=descriptor(t['selection'])
    elif 'point' in t:d=descriptor(t['point'])
    else:d=t
    nested=d.get('task',{});system=d.get('system') or nested.get('system');meta=nested.get('responsibility_meta') or d.get('responsibility_meta')
    if system is None and meta:system=Path(meta).stem
    held=d.get('heldout_fold',nested.get('heldout_fold',t.get('heldout_fold',-1)));return system,held


def main():
    protocol_path=ROOT/'config/SELECTED_JOINT_RECIPE_FRONTIER_PROTOCOL_V1.json';config=read(protocol_path);states={};cache={}
    for source in config['sources']:
        base=ROOT/'runs/selected_joint_recipe_frontier_v1'/Path(source['path']).name
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name='selected_joint_recipe_'+base.name,path=str(base.relative_to(ROOT)),handler='code/r2_scientific_admission.py',handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),kind='custom',priority=24.05,enabled=False))
        queue=read(base/'tasks.json');states[source['path']]=dict(base=base,queue=queue,known={t['id'] for t in queue},pending={t['id']:t for t in queue if not (base/'receipts'/(t['id']+'.json')).exists()})
    while True:
        config=read(protocol_path);targets=set(config['systems']);target_signature=tuple(sorted(targets));registry=read(ROOT/'config/GPU_STAGES.json')['stages'];report={}
        for source in config['sources']:
            name=source['path'];folder=ROOT/name;path=folder/'tasks.json'
            if not path.exists():continue
            state=states[name];base=state['base'];version=path.stat().st_mtime_ns
            if cache.get(name,(None,None))[0]!=version or cache[name][1]!=target_signature:
                selected=[]
                for t in read(path):
                    system,held=identity(t)
                    if system in targets:selected.append((t,system,held))
                selected.sort(key=lambda v:(0 if v[2]>=0 else 1,v[1][-1],v[2],v[0].get('start',0),v[0]['id']));cache[name]=(version,target_signature,selected)
            done={p.stem for p in (folder/'receipts').glob('*.json')};claimed={p.name for p in (folder/'claims').glob('*')}
            for ident,t in list(state['pending'].items()):
                if (base/'receipts'/(ident+'.json')).exists() or t['canonical_task']['id'] in done:state['pending'].pop(ident)
            scientific=min((s for s in registry if s['path']==name),key=lambda s:s['priority']);added=0
            for t,system,held in cache[name][2]:
                if len(state['pending'])>=config['maximum_outstanding_per_source']:break
                ident='selected_joint_recipe_'+digest(dict(stage=name,id=t['id']))[:24]
                if ident in state['known'] or t['id'] in done or t['id'] in claimed:continue
                carrier=dict(id=ident,canonical_stage=name,canonical_task=t,scientific_handler={k:scientific[k] for k in ['handler','handler_sha256','kind']});enqueue(state['queue'],state['known'],carrier);state['pending'][ident]=carrier;added+=1
            if added:atomic(base/'tasks.json',state['queue']);atomic(base/'producer.json',dict(complete=False,tasks=len(state['queue']),time=stamp(),canonical_stage=name))
            report[name]=dict(added=added,outstanding=len(state['pending']),selected_existing_tasks=len(cache[name][2]),canonical_completed=len(done))
        atomic(ROOT/'runs/selected_joint_recipe_frontier_v1/LIVE.json',dict(time=stamp(),sources=report,original_sources_and_models_retained=True,no_synthetic_task_or_modified_seed=True));time.sleep(15)


if __name__=='__main__':main()
