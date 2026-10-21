"""Sparse real-parent evaluation and exact whole-trajectory gate composition."""
from common import *
import traceback
import numpy as np
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_obs_qda_gate import OUT,quadratic
from vlm_obs_gate_policy import test_lock
from vlm_results import summarize,save_npy
from vlm_repair_queue_v6 import stage
from repair_queue_v2 import atomic_unique as atomic

BASE=ROOT/'runs/vlm_global_refine_20261016_v5'
STAGE='final_test_obs_qda_parent_union'


def masks():
    marker=OUT/'TEST_MASKS_READY.json'
    if marker.exists():
        r=read(marker);assert sha(ROOT/r['path'])==r['sha256'];return r
    locked=read(OUT/'FINAL_LOCK.json');policies=list({r['id']:r for r in locked['roles'].values()}.values())
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');feature=OUT/'test_features'
    protocol=read(feature/'PROTOCOL.json');assert protocol['source_lock_sha256']==sha(OUT/'FINAL_LOCK.json')
    cells=protocol['cells'];dims={c:np.load(ROOT/read(VOUT/'cells'/(c+'.json'))['path'],mmap_mode='r').shape[1] for c in cells}
    values={c:np.full((len(rows),dims[c]),np.nan,dtype=np.float32) for c in cells};seen=np.zeros(len(rows),bool);proofs=[]
    for p in sorted((feature/'receipts').glob('*.json')):
        r=read(p);path=ROOT/r['path'];assert sha(path)==r['sha256']
        with np.load(path) as z:
            idx=z['test_indices'];assert not seen[idx].any();assert r['tokens']==[rows[i]['token'] for i in idx]
            for c in cells:values[c][idx]=z[c]
            seen[idx]=True
        proofs.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),array_sha256=r['sha256']))
    assert seen.all();arrays={};records=[]
    with threadpool_limits(2):
        for policy in policies:
            gate=policy['gate'];risk=quadratic(values[gate['fit']['cell']],gate['fit']);mask=np.isfinite(risk)&(risk>gate['threshold'])
            arrays[policy['id']]=mask;arrays[policy['id']+'__risk']=risk
            records.append(dict(id=policy['id'],risk_positive_cases=int(mask.sum()),missing_cases=int((~np.isfinite(risk)).sum())))
    from vlm_scan import save_npz
    path=OUT/'test_masks.npz';h=save_npz(path,**arrays)
    result=dict(status='PASS',time=stamp(),path=str(path.relative_to(ROOT)),sha256=h,records=records,
        source_lock_sha256=sha(OUT/'FINAL_LOCK.json'),feature_proofs=proofs,no_test_labels_for_masks=True)
    atomic(marker,result);return result


def compose(mask_record):
    folder=VOUT/'analysis'/STAGE;raw=np.load(folder/'scores.npy',mmap_mode='r');raw_edits=np.load(folder/'edits.npy',mmap_mode='r')
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');actual_rows=read(folder/'rows.json');positions={r['token']:i for i,r in enumerate(rows)};idx=[positions[r['token']] for r in actual_rows]
    old=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r');base=np.asarray(old[:,:,0,:]);assert np.array_equal(raw[:,:,0,:],base[:,idx,:])
    locked=read(OUT/'FINAL_LOCK.json');policies=list({r['id']:r for r in locked['roles'].values()}.values())
    parents=read(folder/'arms.json');ai={a['id']:i+1 for i,a in enumerate(parents)}
    data=np.repeat(base[:,:,None,:],len(policies)+1,axis=2);edits=np.zeros(data.shape[:-1]+(5,),dtype=np.float32)
    failure=np.repeat(base[:,:,None,:],len(parents)+1,axis=2);masks_np=np.load(ROOT/mask_record['path']);virtual=[]
    for p in parents:
        col=ai[p['id']];selected=np.array(raw[:,:,col,:]);take=base[:,idx,0]<.7
        failure[:,idx,col,:]=np.where(take[:,:,None],selected,base[:,idx,:])
    subset=np.zeros(len(rows),bool);subset[idx]=True
    assert subset[(base[:,:,0]<.7).any(0)].all()
    for i,policy in enumerate(policies,1):
        mask=masks_np[policy['id']];assert subset[mask].all();col=ai[policy['parent']['id']]
        take=mask[idx];data[:,idx,i,:]=np.where(take[None,:,None],raw[:,:,col,:],base[:,idx,:])
        edits[:,idx,i,:]=np.where(take[None,:,None],raw_edits[:,:,col,:],0.)
        virtual.append(next(a for a in read(OUT/'TEST_LOCK.json')['parents'] if a['id']==policy['id']))
    destination=VOUT/'analysis/final_test_obs_qda_gate';sh=save_npy(destination/'scores.npy',data);eh=save_npy(destination/'edits.npy',edits)
    atomic(destination/'rows.json',rows);atomic(destination/'arms.json',virtual)
    atomic(destination/'SUMMARY.json',dict(status='COMPLETE',time=stamp(),coverage_exact=True,
        protocol=dict(seeds=[0,1,2,3,4],scenes=len(rows),arms=len(virtual)),scores_sha256=sh,edits_sha256=eh,
        source_parent_summary_sha256=sha(folder/'SUMMARY.json'),source_mask_sha256=mask_record['sha256'],
        whole_trajectory_choice_is_exact=True,no_uncomputed_nonbase_prediction_invented=True,
        scope='Deployable observation-only gate. All risk-positive outputs actually inferred, including Base successes; all other outputs are Base by definition.'))
    failure_path=OUT/'ungated/failure_gated_scores.npy';fh=save_npy(failure_path,failure)
    atomic(OUT/'ungated/rows.json',rows);atomic(OUT/'ungated/arms.json',parents)
    atomic(OUT/'ungated/ACCEPTANCE.json',dict(status='PASS',time=stamp(),study='observation_qda_gate',
        score_path=str(failure_path.relative_to(ROOT)),scores_sha256=fh,seeds=[0,1,2,3,4],
        scope='Actual same-parent Base-failure-only diagnostic; every failed draw was inferred through the union panel, all nonfailures stay Base by definition. This is not unconditional parent inference.'))
    atomic(OUT/'INFERENCE_COMPLETE.json',dict(status='PASS',time=stamp(),cases=len(rows),seeds=5,
        actual_parent_union_cases=len(actual_rows),actual_parent_union_stage=STAGE,
        no_original_success_false_positive_harm_filtered_out=True))


def main():
    setup('vlm_repair/obs_gate_test');OUT.mkdir(exist_ok=True)
    for p,h in read(VOUT/'OBS_QDA_GATE_TEST_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    while not (OUT/'test_features/COLLECTION_COMPLETE.json').exists():
        if (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists():return
        time.sleep(30)
    test_lock()
    assert read(OUT/'FEATURE_ENGINEERING_PASS.json')['status']=='PASS'
    m=masks();rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json')
    locked=read(OUT/'FINAL_LOCK.json');policies=list({r['id']:r for r in locked['roles'].values()}.values());parents=list({r['parent']['id']:r['parent'] for r in policies}.values())
    # Privileged labels affect only additional diagnostic coverage, never the
    # already frozen observation-only gate or deployed trajectory choice.
    baseline=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r')[:,:,0,:]
    take=(baseline[:,:,0]<.7).any(0)
    with np.load(ROOT/m['path']) as z:
        for p in policies:take|=z[p['id']]
    if not (BASE/'stages'/STAGE/'PROTOCOL.json').exists():
        stage(BASE,STAGE,[r for i,r in enumerate(rows) if take[i]],parents,[0,1,2,3,4],chunk=2,arm_chunk=64)
    while summarize(BASE,STAGE) is None:time.sleep(30)
    compose(m);print('OBSERVATION_QDA_GATE_INFERENCE_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(OUT/'failures/test_controller.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
