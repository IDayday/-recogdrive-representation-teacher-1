"""Prioritize ready complete primary systems; retain all variant computation.

A source may have many partial heterogeneous K2 banks before a ready K3 primary
bank in lexical order. Shadow only all-fivefold-ready primary systems, with exact
canonical claims/handlers; old frontiers keep progressing at reduced share.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from functools import lru_cache
import re


@lru_cache(maxsize=4096)
def description(path):return read(ROOT/path)


def main():
    config_path=ROOT/'config/PRIMARY_COMPLETE_CV_FRONTIER_PROTOCOL_V1.json';config=read(config_path);states={};cache={}
    for source in config['sources']:
        base=ROOT/'runs/primary_complete_cv_frontier_v1'/Path(source['path']).name
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name='primary_complete_cv_'+base.name,path=str(base.relative_to(ROOT)),handler='code/r2_scientific_admission.py',handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),kind='custom',priority=24.1,enabled=False))
        queue=read(base/'tasks.json');states[source['path']]=dict(base=base,queue=queue,known={t['id'] for t in queue},pending={t['id']:t for t in queue if not (base/'receipts'/(t['id']+'.json')).exists()})
    while True:
        config=read(config_path);targets=set(config.get('priority_systems',[]));report={};registry=read(ROOT/'config/GPU_STAGES.json')['stages']
        for source in config['sources']:
            name=source['path'];folder=ROOT/name;path=folder/'tasks.json';state=states[name];base=state['base'];version=path.stat().st_mtime_ns
            if cache.get(name,(None,None))[0]!=version or cache[name][1]!=tuple(sorted(targets)):
                original=read(path);folds={};eligible={}
                for t in original:
                    d=description(t['point']);system=d['system'];held=d['heldout_fold'];m=re.fullmatch(r'(representation|response|correction)_K([2-8])_seed([0-2])',system)
                    if held<0 or m is None or (m[3]!='0' and system not in targets):continue
                    folds.setdefault(system,set()).add(held);eligible[t['id']]=(system,int(m[2]),held)
                ready={s for s,f in folds.items() if set(range(5))<=f};selected=[t for t in original if t['id'] in eligible and eligible[t['id']][0] in ready]
                selected.sort(key=lambda t:(0 if eligible[t['id']][0] in targets else 1,eligible[t['id']][1],eligible[t['id']][0],eligible[t['id']][2],t.get('start',0),t['id']))
                cache[name]=(version,tuple(sorted(targets)),selected,sorted(ready))
            done={p.stem for p in (folder/'receipts').glob('*.json')};owned={p.name for p in (folder/'claims').glob('*')}
            for ident,t in list(state['pending'].items()):
                if (base/'receipts'/(ident+'.json')).exists() or t['canonical_task']['id'] in done:state['pending'].pop(ident)
            scientific=min((s for s in registry if s['path']==name),key=lambda s:s['priority']);added=0
            for t in cache[name][2]:
                if len(state['pending'])>=config['maximum_outstanding_per_source']:break
                ident='primary_ready_'+digest(dict(stage=name,id=t['id']))[:24]
                if t['id'] in done or t['id'] in owned or ident in state['known']:continue
                carrier=dict(id=ident,canonical_stage=name,canonical_task=t,scientific_handler={k:scientific[k] for k in ['handler','handler_sha256','kind']});enqueue(state['queue'],state['known'],carrier);state['pending'][ident]=carrier;added+=1
            if added:atomic(base/'tasks.json',state['queue']);atomic(base/'producer.json',dict(complete=False,tasks=len(state['queue']),time=stamp(),canonical_stage=name,only_complete_fivefold_primary_systems=True))
            report[name]=dict(added=added,outstanding=len(state['pending']),complete_ready_systems=cache[name][3],canonical_completed=len(done))
        atomic(ROOT/'runs/primary_complete_cv_frontier_v1/LIVE.json',dict(time=stamp(),sources=report,existing_variant_frontiers_retained=True,no_scientific_parameters_changed=True));time.sleep(15)


if __name__=='__main__':main()
