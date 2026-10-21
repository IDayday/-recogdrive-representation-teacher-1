"""Bounded ready frontier, prioritizing coherent held systems over all-data backlog.

Only carrier metadata is sorted. Original scientific queues, configurations,
claims, model/trajectory/score programs and outputs remain unchanged. A short
frontier permits newly ready important dependencies to enter without waiting
behind thousands of old metadata items.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
import re
from functools import lru_cache


@lru_cache(maxsize=8192)
def description(path):return read(ROOT/path)


def priority(task,model):
    d=task if model else description(task['point']);held=d['heldout_fold'];system=d.get('system',task.get('system',''))
    match=re.search(r'_K(\d+)_seed([0-2])$',system);assert match,(system,task)
    K=int(match[1]);replicate=int(match[2]);tier=0 if held>=0 and K in [2,3,4] and replicate==0 else 1 if held<0 and K in [2,3,4] and replicate==0 else 2 if held>=0 and replicate==0 else 3
    return (tier,K,system,held,task.get('expert',-1),task.get('block',''),task.get('start',-1),task['id'])


def main():
    config=read(ROOT/'config/MAIN_EXPERT_FRONTIER_KMAJOR_PROTOCOL_V2.json');states={};cache={}
    for source in config['sources']:
        base=ROOT/'runs/main_expert_frontier_kmajor_v2'/Path(source['path']).name
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name='bounded_frontier_'+base.name,path=str(base.relative_to(ROOT)),handler='code/r2_scientific_admission.py',handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),kind='custom',priority=24.2,enabled=False))
        queue=read(base/'tasks.json');states[source['path']]=dict(base=base,queue=queue,known={t['id'] for t in queue},pending={t['id']:t for t in queue if not (base/'receipts'/(t['id']+'.json')).exists()})
    while True:
        report={};registry=read(ROOT/'config/GPU_STAGES.json')['stages']
        for source in config['sources']:
            name=source['path'];folder=ROOT/name;path=folder/'tasks.json';state=states[name];base=state['base']
            if not path.exists():continue
            version=path.stat().st_mtime_ns
            if cache.get(name,(None,None))[0]!=version:cache[name]=(version,sorted(read(path),key=lambda t:priority(t,source.get('model',False))))
            original_done={p.stem for p in (folder/'receipts').glob('*.json')};original_claimed={p.name for p in (folder/'claims').glob('*')}
            for ident,t in list(state['pending'].items()):
                if (base/'receipts'/(ident+'.json')).exists() or t['canonical_task']['id'] in original_done:state['pending'].pop(ident)
            scientific=min((s for s in registry if s['path']==name),key=lambda s:s['priority']);added=0
            for t in cache[name][1]:
                if len(state['pending'])>=config['maximum_outstanding_per_source']:break
                ident='frontier_'+digest(dict(stage=name,id=t['id']))[:24]
                if t['id'] in original_done or t['id'] in original_claimed or ident in state['known']:continue
                carrier=dict(id=ident,canonical_stage=name,canonical_task=t,scientific_handler={k:scientific[k] for k in ['handler','handler_sha256','kind']})
                enqueue(state['queue'],state['known'],carrier);state['pending'][ident]=carrier;added+=1
            if added:atomic(base/'tasks.json',state['queue']);atomic(base/'producer.json',dict(complete=False,tasks=len(state['queue']),time=stamp(),original_canonical_stage=name))
            report[name]=dict(added=added,outstanding=len(state['pending']),canonical_done=len(original_done),original_tasks=len(cache[name][1]))
        atomic(ROOT/'runs/main_expert_frontier_kmajor_v2/LIVE.json',dict(time=stamp(),sources=report,no_scientific_reordering_or_preemption=True))
        time.sleep(15)


if __name__=='__main__':main()
