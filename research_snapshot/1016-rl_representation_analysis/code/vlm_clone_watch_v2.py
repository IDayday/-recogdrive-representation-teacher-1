"""Keep exact failed command signatures while accepting verified replacements."""
from common import *
import argparse
import vlm_clone_watch as previous
from vlm_elastic_registry import DEST

original_resolution=previous.adapter_failure_resolved

def resolved(path):
    if original_resolution(path):return True
    ledger=DEST/'RESOLVED_COMMAND_FAILURES.json'
    if not ledger.exists():return False
    for r in read(ledger)['records']:
        if (ROOT/r['marker']).resolve()!=path.resolve():continue
        actual=read(path)
        if not all(actual.get(k)==v for k,v in r['signature'].items()):return False
        if sha(ROOT/actual['log'])!=r['log_sha256']:return False
        proof=ROOT/r['proof'];state=ROOT/r['replacement_state']
        if sha(proof)!=r['proof_sha256'] or read(proof)['status']!='PASS':return False
        status=read(state);age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(status['time'])).total_seconds()
        return status['pid']==r['replacement_pid'] and status['status'] in ['RUNNING','COMPLETE'] and age<120
    return False

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006');p.add_argument('--period',type=int,default=60)
    p.add_argument('--warn-minutes',type=float,default=30);p.add_argument('--once',action='store_true');a=p.parse_args();assert 1<=a.period<=60
    previous.WATCH=previous.WATCH+[DEST/'analysis_move/SERVICE_READY.json']+[
        ROOT/read(ROOT/n['config'])['folder']/name
        for n in read(DEST/'REGISTRY.json')['nodes'] if n['kind']=='elastic'
        for name in ['FIVE_MINUTE_PHASE_CHECK.json','GPU_QUEUE_FIVE_MINUTE_CHECK.json']]
    previous.adapter_failure_resolved=resolved;previous.main(a)
