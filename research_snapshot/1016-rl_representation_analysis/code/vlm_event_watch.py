"""Foreground terminal returns on a meaningful phase change, failure, or lifetime alarm."""
from common import *
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

WATCH=[VOUT/'global_funnel/PARENT_LOCK.json',VOUT/'global_funnel/FINAL_CANDIDATE_LOCK.json',
       VOUT/'final/PRIMARY_INFERENCE_COMPLETE.json',VOUT/'final/SCIENTIFIC_ACCEPTANCE.json',
       SEM/'CACHE_COMPLETE.json',SEM/'repair/FINAL_LOCK.json',SEM/'repair/INFERENCE_COMPLETE.json',
       SEM/'repair/NO_COMPETITIVE_CANDIDATES.json',SEM/'repair/SCIENTIFIC_ACCEPTANCE.json',
       VOUT/'POSTCOMPUTE_REVIEW_READY.json']

if __name__=='__main__':
    setup('vlm_repair/event_watch');state_path=VOUT/'EVENT_WATCH_SEEN.json';seen=set(read(state_path)['seen']) if state_path.exists() else {str(p.relative_to(ROOT)) for p in WATCH if p.exists()}
    atomic(state_path,dict(time=stamp(),seen=sorted(seen)))
    while True:
        failures=list(VOUT.glob('**/failures/*.json'))
        for run in ['vlm_repair_20261016_v2','vlm_global_refine_20261016_v5','vlm_semantic_20261016_v2']:failures+=list((ROOT/'runs'/run/'failures').glob('*.json'))
        assert not failures,'Experimental failure retained: '+str(failures[:1])
        current={str(p.relative_to(ROOT)) for p in WATCH if p.exists()};new=current-seen
        if new:
            atomic(state_path,dict(time=stamp(),seen=sorted(seen|current)));print('WAKE_AGENT_PHASE_CHANGE',json.dumps(sorted(new)),flush=True);break
        remaining=(dt.datetime(2026,10,17,3,42,10,tzinfo=dt.timezone.utc)-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining<1200:print('WAKE_AGENT_LIFETIME_CHECKPOINT_REQUIRED',flush=True);break
        print(json.dumps(dict(time=stamp(),status='WAITING_MEANINGFUL_PHASE_CHANGE',old_node_hours_left=round(remaining/3600,2))),flush=True)
        time.sleep(60)
