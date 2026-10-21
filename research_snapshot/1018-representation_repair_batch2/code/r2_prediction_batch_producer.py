"""Bounded cohorts of pending critic predictions with identical observable inputs.

Only stage admission changes. Original source tasks, points and receipts remain
authoritative. Checkpoints, subjects, labels and calibration selection stay fixed.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from functools import lru_cache


@lru_cache(maxsize=512)
def point(path):return read(ROOT/path)


def main():
    setup('prediction_batch_producer')
    while not (ROOT/'provenance/CRITIC_SHARED_INPUT_BATCH_ADOPTION.json').exists():time.sleep(15)
    protocol=read(ROOT/'config/CRITIC_SHARED_INPUT_BATCH_PROTOCOL_V1.json');states={}
    for source in protocol['sources']:
        name=Path(source['stage']).name;base=ROOT/'runs/prediction_batch_frontier_v1'/name
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name='shared_critic_inputs_'+name,path=str(base.relative_to(ROOT)),handler='code/r2_prediction_batch.py',handler_sha256=sha(ROOT/'code/r2_prediction_batch.py'),kind='custom',priority=24,enabled=False))
        q=read(base/'tasks.json');covered={(e['stage'],e['task']['id']) for t in q for e in t['entries']};states[source['stage']]=dict(base=base,queue=q,known={t['id'] for t in q},covered=covered)
    while True:
        report={}
        for source in protocol['sources']:
            canonical=ROOT/source['stage'];state=states[source['stage']];base=state['base'];original=canonical/'tasks.json'
            if not original.exists():continue
            tasks=read(original);done={p.stem for p in (canonical/'receipts').glob('*.json')};claimed={p.name for p in (canonical/'claims').glob('*')};pending=[t for t in state['queue'] if not (base/'receipts'/(t['id']+'.json')).exists()];available=max(0,protocol['maximum_outstanding_per_source']-len(pending));groups={};order=[]
            if available:
                for t in tasks:
                    identity=(source['stage'],t['id'])
                    if t['id'] in done or t['id'] in claimed or identity in state['covered']:continue
                    p=point(t['point']);assert len(p['critics'])==1;critic=p['critics'][0]
                    key=digest(dict(handler=source['handler'],mode=p['mode'],held=p['heldout_fold'],parts=p['parts'],items=p['items'][t['start']:t['end']],responses=p['responses'],view=critic.get('context_view','post_valid'),state_mode=critic.get('state_mode')))
                    if key not in groups:groups[key]=[];order.append(key)
                    groups[key].append(dict(stage=source['stage'],task=t,handler=source['handler'],handler_sha256=source['handler_sha256']))
                added=0
                for key in order[:available]:
                    entries=groups[key];spec=dict(entries=entries,input_identity=key);ident='predict_batch_'+digest(spec)[:24];enqueue(state['queue'],state['known'],dict(id=ident,stage=str(base.relative_to(ROOT)),**spec));state['covered'].update((e['stage'],e['task']['id']) for e in entries);added+=1
                if added:atomic(base/'tasks.json',state['queue']);atomic(base/'producer.json',dict(complete=False,time=stamp(),tasks=len(state['queue']),source_stage=source['stage']))
            report[source['stage']]=dict(original_tasks=len(tasks),canonical_done=len(done),cohort_tasks=len(state['queue']),covered_original_tasks=len(state['covered']),pending_before_refill=len(pending))
        atomic(ROOT/'runs/prediction_batch_frontier_v1/LIVE.json',dict(time=stamp(),sources=report,scientific_outputs_unchanged=True));time.sleep(10)


if __name__=='__main__':main()
