"""Bounded compatible original-task cohorts; no model or policy choices."""
from r2_common import *
from r2_resume_support import register_once
from r2_policy_cohort import components
from functools import lru_cache
import argparse
import re


@lru_cache(maxsize=8192)
def descriptor(path):
    point=read(ROOT/path);held=point['heldout_fold'];system=point.get('system','unknown');m=re.search(r'_K([2-8])_seed([0-2])$',system)
    k=int(m[1]) if m else 99;fit=int(m[2]) if m else 9
    return dict(point=point,parts=components(point),panel_sha256=digest(point['panel']),K=k,fit=fit,held=held)


def priority(task,meta):
    system=meta['point'].get('system','unknown')
    if re.fullmatch(r'(representation|response|correction)_K[2-8]_seed[0-2]',system):tier=0
    elif '_capacity_' in system:tier=1
    elif any(v in system for v in ['_causal_','_em1_','_unified_bcs_']):tier=2
    else:tier=3
    stem=re.sub(r'_seed[0-2]$','',system)
    return (tier,0 if meta['K']<=4 else 1,meta['K'],stem,meta['fit'],0 if meta['held']>=0 else 1,meta['held'],-task['start'],task['id'])


def main(args):
    setup('policy_cohort_frontier_'+args.phase)
    config=read(ROOT/'config/POLICY_COHORT_COHERENT_EXECUTION_PROTOCOL_V2.json');handler='code/r2_policy_cohort_dispatch.py';states={};cache={}
    for source in config['sources']:
        name=source['name'];base=ROOT/'runs/policy_cohort_coherent_frontier_v2'/args.phase/name
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name='policy_cohort_coherent_'+args.phase+'_'+name,path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.,enabled=False))
        queue=read(base/'tasks.json');pending={}
        for t in queue:
            if not (base/'receipts'/(t['id']+'.json')).exists():pending[t['id']]=read(ROOT/t['definition'])
        states[name]=dict(base=base,queue=queue,known={t['id'] for t in queue},pending=pending)
    while True:
        assert sha(ROOT/'code/r2_policy_cohort.py')==config['executor_sha256']
        reports={};finished=True
        for source in config['sources']:
            name=source['name'];state=states[name];base=state['base'];original=ROOT/source['stage'];path=original/'tasks.json'
            for ident,d in list(state['pending'].items()):
                if (base/'receipts'/(ident+'.json')).exists():state['pending'].pop(ident)
            limit=config['pilot_cohorts_per_source'] if args.phase=='pilot' else None
            if limit is not None and len(state['queue'])>=limit:
                if state['pending']:finished=False
                reports[name]=dict(published=len(state['queue']),outstanding=len(state['pending']),finite_pilot_admission_complete=True);continue
            finished=False
            if not path.exists():continue
            version=path.stat().st_mtime_ns
            if cache.get(name,(None,None))[0]!=version:cache[name]=(version,read(path))
            done={p.stem for p in (original/'receipts').glob('*.json')};owned={p.name for p in (original/'claims').iterdir()} if (original/'claims').exists() else set()
            reserved={e['task']['id'] for d in state['pending'].values() for e in d['entries']};groups={};fallback=[]
            for t in cache[name][1]:
                if t['id'] in done or t['id'] in owned or t['id'] in reserved:continue
                meta=descriptor(t['point']);point=meta['point'];item=(priority(t,meta),t,meta)
                if point['mode']!='heldout':
                    if args.phase=='full':fallback.append([item])
                    continue
                key=(meta['panel_sha256'],tuple(point['seeds']),point['mode'],meta['held'],t['start'],t['end'])
                groups.setdefault(key,[]).append(item)
            choices=[]
            for entries in groups.values():entries.sort(key=lambda item:item[0]);choices.append(entries)
            choices.extend(fallback);choices.sort(key=lambda entries:entries[0][0]);added=0
            for entries in choices:
                if len(state['pending'])>=config['maximum_outstanding_cohorts']:break
                if limit is not None and len(state['queue'])>=limit:break
                selected=[entries[0]];used=dict(entries[0][2]['parts']);remaining=entries[1:]
                while remaining and len(selected)<config['maximum_logical_points']:
                    eligible=[v for v in remaining if all(k not in used or used[k]==value for k,value in v[2]['parts'].items())]
                    if not eligible:break
                    first_priority=min(v[0][:3] for v in eligible);eligible=[v for v in eligible if v[0][:3]==first_priority]
                    best=min(eligible,key=lambda v:(-len(set(v[2]['parts'])&set(used)),v[0]));selected.append(best);used.update(best[2]['parts']);remaining.remove(best)
                if args.phase=='pilot' and len(selected)<2:continue
                original_tasks=[v[1] for v in selected];ident='policy_cohort_coherent_'+args.phase+'_'+digest(dict(source=source['stage'],original_ids=[t['id'] for t in original_tasks]))[:24]
                if ident in state['known']:continue
                definition=dict(id=ident,stage=str(base.relative_to(ROOT)),phase=args.phase,entries=[dict(stage=source['stage'],task=t,handler=source['handler'],handler_sha256=source['handler_sha256']) for t in original_tasks])
                dp=base/'definitions'/(ident+'.json');assert not dp.exists();atomic(dp,definition)
                t=dict(id=ident,stage=str(base.relative_to(ROOT)),definition=str(dp.relative_to(ROOT)),definition_sha256=sha(dp),executor_sha256=sha(ROOT/'code/r2_policy_cohort.py'))
                state['queue'].append(t);state['known'].add(ident);state['pending'][ident]=definition;added+=1
            if added:atomic(base/'tasks.json',state['queue']);atomic(base/'producer.json',dict(time=stamp(),tasks=len(state['queue']),complete=limit is not None and len(state['queue'])>=limit,phase=args.phase))
            reports[name]=dict(published=len(state['queue']),outstanding=len(state['pending']),added=added,unclaimed_compatible_groups=len(groups),original_canonical_completed=len(done),source_tasks=len(cache[name][1]))
        folder=ROOT/'runs/policy_cohort_coherent_frontier_v2'/args.phase;atomic(folder/'LIVE.json',dict(time=stamp(),sources=reports,original_tasks_and_source_preserved=True))
        if args.phase=='pilot' and finished:
            atomic(folder/'COMPLETE.json',dict(time=stamp(),sources=reports,mechanical_completion_only=True,requires_agent_scientific_and_throughput_acceptance=True));return
        time.sleep(15)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',required=True,choices=['pilot','full']);main(p.parse_args())
