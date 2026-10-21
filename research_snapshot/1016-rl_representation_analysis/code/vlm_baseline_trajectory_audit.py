"""Compare every final-test Base trajectory, beyond equality of PDM score fields."""
from common import *
import argparse
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_scan import save_npz
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup('vlm_repair/base_trajectory_audit');stage='final_test_semantic' if a.study=='semantic' else 'final_test';new=ROOT/'runs/vlm_global_refine_20261016_v5';old=ROOT/'runs/candidate_repair_20261016_v1';dest=SEM/'repair' if a.study=='semantic' else VOUT/'final'
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');index={r['token']:i for i,r in enumerate(rows)};shape=(5,len(rows),8,3)
    cached=VOUT/'final/original_base_trajectories.npz';proof_path=cached.with_suffix('.json')
    if not proof_path.exists():
        values=np.full(shape,np.nan,dtype=np.float64);seen=np.zeros(shape[:2],dtype=bool);sources=[]
        for path in sorted((old/'results').glob('final_test_s*.json')):
            proof=read(old/'receipts'/path.name);assert sha(path)==proof['result_sha256'];d=read(path);assert d['task']['stage']=='final_test'
            for r in d['records']:
                if r['arm']!='baseline':continue
                j=r['seed_index'];i=index[r['token']];assert r['seed']==seed(r['token'],j);v=np.asarray(r['trajectory'],dtype=np.float64)
                if seen[j,i]:assert np.array_equal(values[j,i],v)
                else:values[j,i]=v;seen[j,i]=True
            sources.append(dict(path=str(path.relative_to(ROOT)),sha256=proof['result_sha256']))
        assert seen.all() and np.isfinite(values).all();h=save_npz(cached,trajectories=values)
        atomic(proof_path,dict(status='PASS',time=stamp(),sources=sources,array_sha256=h,rows_sha256=digest(rows),seeds=[0,1,2,3,4]))
    proof=read(proof_path);assert sha(cached)==proof['array_sha256'] and proof['rows_sha256']==digest(rows)
    with np.load(cached) as f:reference=np.array(f['trajectories'])
    seen=np.zeros(shape[:2],dtype=bool);sources=[]
    for path in sorted((new/'results').glob(stage+'_a*.json')):
        p=read(new/'receipts'/path.name);assert sha(path)==p['result_sha256'];d=read(path);assert d['task']['stage']==stage
        for r in d['records']:
            if r['arm']!='baseline':continue
            j=r['seed_index'];i=index[r['token']];assert r['seed']==seed(r['token'],j)
            assert np.array_equal(np.asarray(r['trajectory'],dtype=np.float64),reference[j,i]),(r['token'],j)
            seen[j,i]=True
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=p['result_sha256']))
    assert seen.all();atomic(dest/'BASE_TRAJECTORY_ACCEPTANCE.json',dict(status='PASS',time=stamp(),study=a.study,cases=len(rows),seeds=5,trajectories=int(seen.sum()),all_coordinates_bit_exact=True,source_reference_sha256=proof['array_sha256'],current_sources=sources))
    print('ALL_FINAL_BASE_TRAJECTORIES_EXACT',a.study,int(seen.sum()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',choices=['primary','semantic'],required=True);main(p.parse_args())
