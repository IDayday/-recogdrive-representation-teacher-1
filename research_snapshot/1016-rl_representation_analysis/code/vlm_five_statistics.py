"""Joint five-batch inference and recognition-versus-operator diagnostics."""
from common import *
import copy
import numpy as np
from vlm_core import VOUT
from vlm_obs_qda_gate import OUT
from vlm_obs_gate_test import STAGE
from vlm_final_statistics import comparisons
from repair_oracle_extended import detail
from repair_queue_v2 import atomic_unique as atomic


def diagnostics(study):
    folder=VOUT/'analysis/final_test_obs_qda_gate';scores=np.load(folder/'scores.npy',mmap_mode='r')
    base=np.asarray(scores[:,:,0,:]);rows=read(folder/'rows.json');arms=read(folder/'arms.json')
    failure=np.load(ROOT/read(OUT/'ungated/ACCEPTANCE.json')['score_path'],mmap_mode='r')
    parents=read(OUT/'ungated/arms.json');pi={a['id']:i+1 for i,a in enumerate(parents)}
    raw=np.load(VOUT/'analysis'/STAGE/'scores.npy',mmap_mode='r');raw_rows=read(VOUT/'analysis'/STAGE/'rows.json')
    positions={r['token']:i for i,r in enumerate(rows)};idx=np.array([positions[r['token']] for r in raw_rows]);raw_arms=read(VOUT/'analysis'/STAGE/'arms.json');ri={a['id']:i+1 for i,a in enumerate(raw_arms)}
    failed=base[:,:,0]<.7;records=[]
    with np.load(ROOT/read(OUT/'TEST_MASKS_READY.json')['path']) as z:
        for i,a in enumerate(arms,1):
            mask=np.array(z[a['id']]);parent=np.asarray(failure[:,:,pi[a['underlying_arm_id']],:])
            positive=failed&(parent[:,:,0]>base[:,:,0]);benefit=np.where(positive[:,:,None],parent,base)
            # Observation-only gates cannot identify which random draw fails.
            # These scene-constant bounds explicitly include the harms on
            # successful draws of an unstable-failure scene.
            conditional=base.copy();value=np.asarray(raw[:,:,ri[a['underlying_arm_id']],:]);conditional[:,idx,:]=value
            gain=conditional[:,:,0].mean(0)>base[:,:,0].mean(0)
            need=failed.any(0);stable=failed.all(0)
            fixed=np.where((need&gain)[None,:,None],conditional,base)
            stable_fixed=np.where((stable&gain)[None,:,None],conditional,base)
            records.append(dict(id=a['id'],underlying_arm=a['underlying_arm_id'],
                risk_positive_cases=int(mask.sum()),risk_positive_outputs=int(mask.sum()*5),
                failure_precision_of_risk=float((failed&mask[None,:]).sum()/max(mask.sum()*5,1)),
                failure_recall_of_risk=float((failed&mask[None,:]).sum()/max(failed.sum(),1)),
                stable_failure_case_recall=float((stable&mask).sum()/max(stable.sum(),1)),
                actual=detail(np.asarray(scores[:,:,i,:]),base,rows,ci=True),
                same_parent_per_draw_failure_only=detail(parent,base,rows,ci=True),
                same_parent_failure_and_benefit=detail(benefit,base,rows,ci=True),
                same_parent_scene_constant_need_and_benefit=detail(fixed,base,rows,ci=True),
                same_parent_stable_failure_scene_constant_benefit=detail(stable_fixed,base,rows,ci=True),
                no_unconditional_parent_prediction_assumed=True))
    return records


def main():
    setup('vlm_repair/five_statistics')
    pointer=read(VOUT/'ALL_FOUR_STATISTICS_LATEST.json');previous_path=ROOT/pointer['path'];assert sha(previous_path)==pointer['sha256']
    previous=read(previous_path);studies=copy.deepcopy(previous['studies'])
    complete=(OUT/'SCIENTIFIC_ACCEPTANCE.json').exists();assert complete or (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists()
    extra=[]
    if complete:
        s=comparisons(VOUT/'analysis/final_test_obs_qda_gate',read(OUT/'TEST_LOCK.json'))
        s['study']='observation_qda_gate'
        for r in s['contrasts']:r['study']='observation_qda_gate'
        extra=diagnostics(s);s['recognition_operator_diagnostics']=extra;studies.append(s)
    contrasts=[c for s in studies for c in s['contrasts']]
    for family in {c['family'] for c in contrasts}:
        group=sorted([c for c in contrasts if c['family']==family],key=lambda c:c['p_one_sided']);highest=0.
        for i,c in enumerate(group):highest=max(highest,min(1.,c['p_one_sided']*(len(group)-i)));c['p_holm']=highest
    destination=VOUT/'statistics_five'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    result=dict(previous,time=stamp(),studies=studies,observation_gate_complete=complete,
        observation_gate_no_competitive=(OUT/'NO_COMPETITIVE_CANDIDATES.json').exists(),
        all_five_batches_jointly_corrected=True,original_statistics_path=str(previous_path.relative_to(ROOT)),
        original_statistics_sha256=sha(previous_path),recognition_operator_diagnostics=extra,code_sha256=sha(Path(__file__)))
    atomic(destination/'FINAL_STATISTICS.json',result)
    atomic(VOUT/'ALL_FIVE_STATISTICS_LATEST.json',dict(path=str((destination/'FINAL_STATISTICS.json').relative_to(ROOT)),sha256=sha(destination/'FINAL_STATISTICS.json')))
    print('ALL_FIVE_BATCHES_STATISTICS_PASS',len(studies),flush=True)


if __name__=='__main__':main()
