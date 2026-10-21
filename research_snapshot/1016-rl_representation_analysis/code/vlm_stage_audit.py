from common import *
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic
import numpy as np

def main():
    base=ROOT/'runs/vlm_repair_20261016_v2';records=0;checks=[];armmap={}
    for p in (base/'stages').glob('*/arms.json'):
        armmap.update({a['id']:a for a in read(p)})
    latest={}
    for receipt in sorted((base/'receipts').glob('*.json')):
        proof=read(receipt);latest[proof['rank']]=dict(rank=proof['rank'],last_result=str(base/'results'/receipt.name))
    if len(latest)!=32:print('WAIT_ALL_32',len(latest));return
    states=list(latest.values())
    for state in states:
        path=Path(state['last_result']);result=read(path);proof=read(base/'receipts'/path.name);assert sha(path)==proof['result_sha256'];tokens=set()
        for r in result['records']:
            assert r['seed']==seed(r['token'],r['seed_index']);assert r['quality']==quality(r['score']['score']);trajectory=np.asarray(r['trajectory']);assert trajectory.shape==(8,3) and np.isfinite(trajectory).all()
            assert all(np.isfinite(v) and 0<=v<=1+1e-8 for v in r['score'].values())
            if r['arm']!='baseline':assert r['edit']['relative_edit_max']<=armmap[r['arm']]['cap']+1e-6
            tokens.add(r['token']);records+=1
        checks.append(dict(rank=state['rank'],task=result['task'],cases=len(tokens),records=len(result['records']),sha256=proof['result_sha256']))
    failures=list((base/'failures').glob('*.json'));assert not failures
    atomic(VOUT/'REPAIR_STAGE_AUDIT.json',dict(status='PASS',time=stamp(),cards=32,records=records,checks=checks,all_seed_shape_score_quality_caps_checked=True,native_train_baseline_exact_asserted_in_each_task=True))
    print('ALL_32_REPAIR_STAGE_AUDIT_PASS',records)
if __name__=='__main__':main()
