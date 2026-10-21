"""Foreground monitor for all current CPU/GPU queues and the finite DLC lifetime."""
from common import *
from vlm_core import VOUT
from vlm_monitor import snapshot
from vlm_progress import show

if __name__=='__main__':
    setup('vlm_repair/monitor_v2')
    while True:
        try:
            failures=list(VOUT.glob('**/failures/*.json'))
            for run in ['vlm_repair_20261016_v2','candidate_repair_20261016_v1','vlm_global_refine_20261016_v5','vlm_semantic_20261016_v2']:
                failures+=list((ROOT/'runs'/run/'failures').glob('*.json'))
            if failures:raise RuntimeError('Failure with original trace retained: '+str(failures[0]))
            state=snapshot();show()
            if state['all_heavy_complete']:break
        except (OSError,TimeoutError) as e:print(json.dumps(dict(time=stamp(),transient=type(e).__name__)),flush=True);time.sleep(10);continue
        time.sleep(60)
