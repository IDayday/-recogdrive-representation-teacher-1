"""Independent scoring and full-train/validation replay for the late locked study."""
from common import *
import numpy as np
from vlm_core import VOUT
DEST=VOUT/'qda_neighbor_repair'
from vlm_final_accept import audit32,rescore
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/qneighbor_accept')
    assert read(DEST/'INFERENCE_COMPLETE.json')['status']=='PASS'
    assert read(DEST/'FINAL_OPERATOR_ENGINEERING_PASS.json')['status']=='PASS'
    for p,h in read(VOUT/'QDA_EARLY_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    stage='final_test_qneighbor';folder=VOUT/'analysis'/stage
    checks=audit32(stage);independent=rescore(stage,DEST/'independent_rescore')
    scores=np.load(folder/'scores.npy',mmap_mode='r')
    old=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r')
    assert np.array_equal(scores[:,:,0,:],old[:,:,0,:])
    summary=read(folder/'SUMMARY.json')
    assert summary['coverage_exact'] and summary['protocol']['seeds']==[0,1,2,3,4]
    train=VOUT/'analysis/navtrain_qneighbor_locked';validation=VOUT/'analysis/validation_qneighbor'
    tr=read(train/'rows.json');vr=read(validation/'rows.json');index={r['token']:i for i,r in enumerate(tr)}
    idx=[index[r['token']] for r in vr];a=np.load(train/'scores.npy',mmap_mode='r');b=np.load(validation/'scores.npy',mmap_mode='r')
    ta=read(train/'arms.json');va=read(validation/'arms.json');vi={arm['id']:i+1 for i,arm in enumerate(va)}
    original=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')
    old_rows=read(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/rows.json')
    assert len(tr)==103288 and len(vr)==17475 and [r['token'] for r in tr]==[r['token'] for r in old_rows]
    assert np.array_equal(a[:,:,0,:],original[:,:,0,:]) and np.array_equal(a[:,idx,0,:],b[:,:,0,:])
    for i,arm in enumerate(ta,1):assert arm==va[vi[arm['id']]-1] and np.array_equal(a[:,idx,i,:],b[:,:,vi[arm['id']],:])
    result=dict(status='PASS',time=stamp(),study='qda_neighbors',all_32_rank_checks=checks,rescore=independent,
        score_sha256=sha(folder/'scores.npy'),test_baseline_all_seven_fields_exact=True,
        fulltrain_cases=len(tr),validation_cases=len(vr),training_seeds=3,
        fulltrain_baseline_exact=True,validation_subset_all_seven_fields_exact=True)
    atomic(DEST/'SCIENTIFIC_ACCEPTANCE.json',result);print('LATE_SCIENTIFIC_ACCEPTANCE_PASS',flush=True)


if __name__=='__main__':main()
