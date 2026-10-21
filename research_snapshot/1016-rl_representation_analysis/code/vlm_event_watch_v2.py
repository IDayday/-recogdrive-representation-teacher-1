"""Foreground wakeups without descending into mutable queue-claim directories."""
from common import *
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
from vlm_event_watch import WATCH

RUNS=['candidate_repair_20261016_v1','vlm_repair_20261016_v2',
      'vlm_global_refine_20261016_v5','vlm_semantic_20261016_v2']

def errors():
    folders=[VOUT/'failures',VOUT/'early_interface/failures',SEM/'failures',
             SEM/'overlap/failures',SEM/'cpu_extra/failures',SEM/'cpu_wave/failures',
             ROOT/'provenance/fold_backup_errors']
    folders += [ROOT/'runs'/r/'failures' for r in RUNS]
    found=[]
    for folder in folders:
        try:found += list(folder.glob('*.json'))
        except FileNotFoundError:continue
    return found

if __name__=='__main__':
    setup('vlm_repair/event_watch_v2')
    state_path=VOUT/'EVENT_WATCH_SEEN_v2.json'
    watch=WATCH+[VOUT/'fold_backup/ALL_BACKUPS_COMPLETE.json',
                 SEM/'COLLECTION_COMPLETE.json',SEM/'ANALYSIS_EXECUTION.json']
    seen=set(read(state_path)['seen']) if state_path.exists() else {str(p.relative_to(ROOT)) for p in watch if p.exists()}
    atomic(state_path,dict(time=stamp(),seen=sorted(seen)))
    while True:
        try:
            failures=errors()
            assert not failures,'Experimental/auxiliary failure retained: '+str(failures[:1])
            current={str(p.relative_to(ROOT)) for p in watch if p.exists()}
            if current-seen:
                atomic(state_path,dict(time=stamp(),seen=sorted(seen|current)))
                print('WAKE_AGENT_PHASE_CHANGE',json.dumps(sorted(current-seen)),flush=True);break
            remaining=(dt.datetime(2026,10,17,3,42,10,tzinfo=dt.timezone.utc)-dt.datetime.now(dt.timezone.utc)).total_seconds()
            if remaining<1200:print('WAKE_AGENT_LIFETIME_CHECKPOINT_REQUIRED',flush=True);break
            print(json.dumps(dict(time=stamp(),status='WAITING_MEANINGFUL_PHASE_CHANGE',old_node_hours_left=round(remaining/3600,2))),flush=True)
        except (OSError,TimeoutError) as exc:
            print(json.dumps(dict(time=stamp(),transient=type(exc).__name__)),flush=True)
        time.sleep(60)
