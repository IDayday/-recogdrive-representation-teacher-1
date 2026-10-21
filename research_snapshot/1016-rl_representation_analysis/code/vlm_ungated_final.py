"""Predetermined final-policy ungated diagnostics on actual Base failures only."""
from common import *
import copy,traceback
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_repair_queue_v6 import stage
from vlm_results import summarize,save_npy
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_global_refine_20261016_v5'

def needs_ungating(a):
    return any(needs_ungating(p) for p in a['parts']) if a['method']=='combination' else a.get('gate','none')!='none'

def ungate(parent):
    a=copy.deepcopy(parent)
    if a['method']=='combination':a['parts']=[ungate(p) if needs_ungating(p) else p for p in a['parts']]
    else:a['gate']='none';a.pop('gate_threshold',None)
    a.pop('id');a['ungated_parent']=parent['id'];a['oracle_diagnostic']=True;a['id']='vlm_ungated_'+digest(a)[:18];return a

def one(study,lock_path,dest):
    if (dest/'ACCEPTANCE.json').exists():return read(dest/'ACCEPTANCE.json')
    lock=read(lock_path);parents=lock['parents'];arms=list({a['id']:a for a in [ungate(p) for p in parents if needs_ungating(p)]}.values())
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');original=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r');base=np.asarray(original[:,:,0,:]);assert base.shape==(5,12146,7)
    lockfile=dest/'LOCK.json'
    if not lockfile.exists():atomic(lockfile,dict(status='FROZEN_BEFORE_DIAGNOSTIC',time=stamp(),study=study,parents=parents,arms=arms,source_lock_sha256=sha(lock_path),rule='Remove existing internal gates only, preserving actual operators/strengths/fits/caps; infer all and only Base<70 outputs for each fixed seed; nonfailures retain exact Base. No test-based selection.',seeds=[0,1,2,3,4]))
    assert read(lockfile)['arms']==arms
    for j in range(5):
        indices=np.flatnonzero(base[j,:,0]<.7);name=f'final_test_{study}_ungated_failures_s{j}'
        if arms and len(indices) and not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,[rows[i] for i in indices],arms,[j],chunk=2,arm_chunk=64)
    matrix=np.repeat(base[:,:,None,:],len(arms)+1,axis=2);checks=[];inferred=0
    for j in range(5):
        indices=np.flatnonzero(base[j,:,0]<.7);name=f'final_test_{study}_ungated_failures_s{j}'
        if not arms or not len(indices):continue
        while True:
            result=summarize(BASE,name)
            if result is not None:break
            time.sleep(20)
        folder=VOUT/'analysis'/name;scores=np.load(folder/'scores.npy',mmap_mode='r');actual_rows=read(folder/'rows.json');assert [r['token'] for r in actual_rows]==[rows[i]['token'] for i in indices]
        assert result['protocol']['seeds']==[j] and np.array_equal(scores[0,:,0,:],base[j,indices,:]);matrix[j,indices,:,:]=scores[0]
        inferred+=len(indices)*(len(arms)+1);checks.append(dict(seed_index=j,failed_cases=len(indices),fresh_baseline_all_seven_fields_exact=True,stage=name))
    path=dest/'failure_gated_scores.npy';hashed=save_npy(path,matrix)
    atomic(dest/'arms.json',arms);atomic(dest/'rows.json',rows)
    result=dict(status='PASS',time=stamp(),study=study,cases=12146,seeds=[0,1,2,3,4],arms=arms,checks=checks,actually_inferred_records=inferred,
        score_path=str(path.relative_to(ROOT)),scores_sha256=hashed,scope='An external Base-failure-gated ungated operator. Uncomputed nonfailures are exactly Base by definition; never interpret this as unconditional ungated inference.')
    atomic(dest/'ACCEPTANCE.json',result);return result

def main():
    setup('vlm_repair/ungated_final')
    primary=VOUT/'final';semantic=SEM/'repair'
    while not (primary/'PRIMARY_STAGES_APPENDED.json').exists():time.sleep(20)
    assert read(primary/'ENGINEERING_PASS.json')['status']=='PASS'
    one('primary',primary/'TEST_LOCK.json',primary/'ungated')
    while True:
        if (semantic/'NO_COMPETITIVE_CANDIDATES.json').exists():break
        if (semantic/'ENGINEERING_PASS.json').exists() and (BASE/'stages/final_test_semantic/PROTOCOL.json').exists():
            one('semantic',semantic/'TEST_LOCK.json',semantic/'ungated');break
        time.sleep(20)
    atomic(VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json',dict(status='PASS',time=stamp(),primary=True,semantic_computed=(semantic/'ungated/ACCEPTANCE.json').exists(),semantic_no_competitive=(semantic/'NO_COMPETITIVE_CANDIDATES.json').exists(),all_methods_oracle_must_be_refreshed=True))
    print('ALL_VLM_UNGATED_TEST_DIAGNOSTICS_COMPLETE',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as e:
        atomic(VOUT/'failures/ungated_final.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
