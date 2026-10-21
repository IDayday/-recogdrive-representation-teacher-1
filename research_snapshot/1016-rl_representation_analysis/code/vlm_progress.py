from common import *
from collections import Counter
from vlm_core import VOUT

def show():
    value=dict(time=stamp())
    for phase in ['rapid','scan','early_interface/scan']:
        b=VOUT/phase;states=[read(p) for p in (b/'workers').glob('rank[0-9][0-9][0-9].json')]
        value[phase]=dict(done=len(list((b/'receipts').glob('*.json'))),total=41 if phase.startswith('early') else 2272,workers=dict(Counter(s['status'] for s in states)))
    for run in ['candidate_repair_20261016_v1','vlm_repair_20261016_v2','vlm_global_refine_20261016_v5','vlm_semantic_20261016_v2']:
        b=ROOT/'runs'/run;states=[read(p) for p in (b/'workers').glob('rank[0-9][0-9][0-9].json')]
        value[run]=dict(done=len(list((b/'receipts').glob('*.json'))),total=len(read(b/'tasks.json')),workers=dict(Counter(s['status'] for s in states)))
    value['cells']=len(list((VOUT/'cells').glob('*.json')))
    value['failures']=[str(p.relative_to(ROOT)) for p in VOUT.glob('**/failures/*.json')]
    atomic(VOUT/'PROGRESS.json',value);print(json.dumps(value),flush=True);return value
if __name__=='__main__':show()
