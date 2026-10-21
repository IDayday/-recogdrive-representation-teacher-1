"""Prove both task-owned original jobs and every reported pod are terminal."""
from common import *
from vlm_resume import old_status,TERMINAL
POD_TERMINAL={'Succeeded','Failed','Stopped','Deleted','Terminated','Completed'}

def assert_quiescent():
    observations=[]
    for index in range(2):
        states=old_status()
        assert all(s['status'] in TERMINAL for s in states),'An original job is still active; no mutation permitted.'
        assert all(p['status'] in POD_TERMINAL for s in states for p in s['pods']), 'A pod is not yet terminal; no mutation permitted.'
        observations.append(dict(time=stamp(),jobs=states))
        if index==0:time.sleep(10)
    return observations

if __name__=='__main__':
    setup('vlm_repair/quiescence');print(json.dumps(assert_quiescent()),flush=True)
