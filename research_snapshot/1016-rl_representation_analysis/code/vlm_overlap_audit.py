"""Early actual-output acceptance during concurrent collection and frozen inference."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_semantic_v2/overlap_audit')
    for execution in [SEM/'OVERLAP_EXECUTION.json',SEM/'EXECUTION.json',VOUT/'REPAIR_EXECUTION_v2.json']:
        for path,h in read(execution)['code_sha256'].items():assert sha(ROOT/path)==h,path
    start=max(read(SEM/f'overlap/smoke/rank{r:03d}.json')['time'] for r in [64,65,66,67]);checks=[];base=ROOT/'runs/vlm_semantic_20261016_v2';groups={r:[] for r in [64,65,66,67]};panel=read(base/'panel.json')
    for path in (base/'receipts').glob('*.json'):
        p=read(path)
        if p['rank'] in groups:groups[p['rank']].append((p['time'],path,p))
    seen=set()
    for rank,items in groups.items():
        assert len(items)>=2
        for _,path,p in sorted(items)[-2:]:
            output=base/'results'/path.name;assert sha(output)==p['result_sha256'];r=read(output);assert sha(ROOT/r['array_path'])==r['array_sha256'];task=r['task'];rows=panel[task['start']:task['end']]
            assert [x['token'] for x in rows]==[x['token'] for x in r['records']]
            with np.load(ROOT/r['array_path']) as z:
                assert np.array_equal(z['global_indices'],[x['global_index'] for x in rows]);assert len(z.files)==33
                for name in z.files:
                    if name!='global_indices':assert z[name].shape[:2]==(len(rows),2) and z[name].dtype==np.float32 and np.isfinite(z[name]).all()
                assert not set(z['global_indices'])&seen;seen.update(z['global_indices'].tolist())
            for row in r['records']:assert row['boundaries']['command_tokens']>0 and row['boundaries']['requirements_tokens']>0
            checks.append(dict(rank=rank,task=task['id'],cases=len(rows),source_sha256=r['array_sha256']))
    inference=ROOT/'runs/vlm_repair_20261016_v2';latest={}
    for path in (inference/'receipts').glob('*.json'):
        p=read(path)
        if p['time']>=start and (p['rank'] not in latest or p['time']>latest[p['rank']][0]):latest[p['rank']]=(p['time'],path,p)
    assert set(latest)==set(range(32));main_checks=[];records=0
    for rank,(_,path,p) in latest.items():
        output=inference/'results'/path.name;assert sha(output)==p['result_sha256'];d=read(output);arms={a['id']:a for a in read(inference/'stages'/d['task']['stage']/'arms.json')}
        for r in d['records']:
            assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(r['score']['score'])
            assert np.asarray(r['trajectory']).shape==(8,3) and np.isfinite(r['trajectory']).all()
            assert r['edit']['relative_edit_max']<=arms.get(r['arm'],{}).get('cap',0)+1e-6
            assert all(np.isfinite(x) and 0<=x<=1+1e-8 for x in r['score'].values());records+=1
        main_checks.append(dict(rank=rank,shared_gpu=rank in [14,15,30,31],task=d['task']['id'],sha256=p['result_sha256']))
    failures=list((SEM/'overlap/failures').glob('*.json'))+list((inference/'failures').glob('*.json'))+list((base/'failures').glob('*.json'));assert not failures
    dest=SEM/'overlap'/('EARLY_AUDIT_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json');atomic(dest,dict(status='PASS',time=stamp(),only_post_overlap_inference_records=True,main_cards=32,main_records=records,main_checks=main_checks,semantic_cases=len(seen),semantic_checks=checks,new_and_original_code_unchanged=True,baseline_exact_assertions_remained_active_per_frozen_task=True));print('OVERLAP_ACTUAL_OUTPUT_AUDIT_PASS',records,len(seen),str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
