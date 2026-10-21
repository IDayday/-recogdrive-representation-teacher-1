"""Queue-only reservations prioritize one canonical full grid in every model layer.

No frozen mathematics or worker code changes. Reservations never count as results.
Every held claim has an explicit scheduler owner, durable history and safe release.
"""
from common import *
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

SCHED='vlm_full_grid_breadth_first_20261016'

def reserve():
    base=VOUT/'scan';tasks=read(base/'tasks.json');core=[];held=[];already=[]
    for task in tasks:
        canonical='patch_mean' if task['block'].startswith(('vision','bridge')) else 'valid_mean'
        if task['cell']==task['block']+'__'+canonical:core.append(task);continue
        directory=base/'claims'/task['id']
        try:directory.mkdir()
        except FileExistsError:already.append(task['id']);continue
        owner=dict(status='SCHEDULER_RESERVED',scheduler=SCHED,time=stamp(),task=task,reason='one canonical full ks/kf/r grid per layer first; all-token full-r PCA fast pass remains independent; reservation is pending, never completed')
        atomic(directory/'OWNER.json',owner);held.append(task['id'])
    atomic(VOUT/'FULL_GRID_SCHEDULE.json',dict(status='ACTIVE',time=stamp(),scheduler=SCHED,canonical=core,held=held,already_worker_claimed=already,scope_unchanged=True,complete_claims_exclude_scheduler_reservations=True))
    print('FULL_GRID_BREADTH_FIRST',len(core),'RESERVED',len(held),'ALREADY_CLAIMED',len(already),flush=True)

def release(task):
    base=VOUT/'scan';directory=base/'claims'/task['id'];owner=read(directory/'OWNER.json');assert owner.get('scheduler')==SCHED and owner['status']=='SCHEDULER_RESERVED'
    atomic(VOUT/'schedule_history'/(task['id']+'.json'),dict(status='RELEASED_TO_WORKERS',time=stamp(),prior_owner=owner))
    (directory/'OWNER.json').unlink();directory.rmdir()

def follow():
    tasks=read(VOUT/'scan/tasks.json');byblock={}
    for task in tasks:byblock.setdefault(task['block'],[]).append(task)
    while True:
        config=read(VOUT/'FULL_GRID_SCHEDULE.json');ready={p.stem for p in (VOUT/'cells').glob('*.json')};done={p.stem for p in (VOUT/'scan/receipts').glob('*.json')};history={p.stem for p in (VOUT/'schedule_history').glob('*.json')}
        released=[]
        for canonical in config['canonical']:
            block=canonical['block']
            if canonical['id'] not in done:continue
            candidates=[t for t in byblock[block] if t['id'] in config['held'] and t['id'] in ready and t['id'] not in history]
            active=[t for t in byblock[block] if t['id'] in history and t['id'] not in done]
            if active or not candidates:continue
            # After canonical coverage, evaluate the strongest all-token CV region next.
            def priority(t):
                path=VOUT/'rapid/results'/(t['id']+'.json')
                if not path.exists():return -1.
                r=read(path)
                if r['status']!='COMPLETE':return -2.
                values=[v['metrics']['auc'] for v in r['shortlisted'] if v['metrics']['auc'] is not None]
                return max(values,default=-2.)
            chosen=max(candidates,key=priority);release(chosen);released.append(chosen['id'])
        atomic(VOUT/'FULL_GRID_SCHEDULE_STATUS.json',dict(time=stamp(),canonical_done=len([t for t in config['canonical'] if t['id'] in done]),canonical_total=len(config['canonical']),full_cells_done=len(done),pending_reservations=len(config['held'])-len(history)-len(released),newly_released=released))
        if len(done)==len(tasks):break
        time.sleep(60)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['reserve','follow']);a=p.parse_args();setup('vlm_repair/full_schedule');globals()[a.mode]()
