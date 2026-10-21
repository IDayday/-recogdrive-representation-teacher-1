"""Corrected-span candidate repair is independent of the already frozen primary study."""
from common import *
from vlm_semantic import SEM
from vlm_core import VOUT
from vlm_selection import block_candidates,confirm,finite
from vlm_fits import make
from vlm_funnel import arms
from vlm_replay import choose
from vlm_global_funnel import choose_parents,selected,refined_arms
from vlm_results import summarize
from vlm_repair_queue_v6 import stage
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_global_refine_20261016_v5';DEST=SEM/'repair'

def wait(name):
    while True:
        result=summarize(BASE,name)
        if result is not None:return result
        time.sleep(30)

def put(name,rows,choices,seeds,chunk=2):
    if not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,rows,choices,seeds,chunk=chunk,arm_chunk=64)
    return wait(name)

def main():
    setup('vlm_semantic_v2/repair');from threadpoolctl import threadpool_limits
    DEST.mkdir(exist_ok=True)
    while not (SEM/'ANALYSIS_EXECUTION.json').exists():time.sleep(30)
    while len(list((SEM/'rapid/receipts').glob('*.json')))!=64:time.sleep(30)
    plan=read(SEM/'PIVOT_PLAN.json');coarse=read(VOUT/'development/COARSE_PANEL.json');replay=read(VOUT/'replay/PANEL.json');fits=[]
    for block in plan['blocks']:
        path=DEST/'selections'/(block['name']+'.json')
        if not path.exists():
            selection=block_candidates(block['name'],SEM);assert selection is not None
            # A physical semantic region is kept only with actual discrimination;
            # all region distributions and the full search remain archived.
            selection['selected']=[r for r in selection['selected'] if finite(r['metrics']['auc'])>=.6 and finite(r['metrics']['standardized_gap'])>=.2 and finite(r['metrics']['weighted_ap'])>finite(r['metrics']['class_prevalence'])]
            atomic(path,selection)
        for spec in read(path)['selected']:
            with threadpool_limits(limits=2):fit=make(spec);confirmation=confirm(fit)
            fits.append(fit);atomic(DEST/'fits'/(fit['id']+'.json'),dict(fit=fit,confirmation=confirmation))
    # Preserve primary locked test/train ordering. Compatible new work then shares
    # the same 32-worker queue, without changing any original experiment.
    while not (VOUT/'final/PRIMARY_STAGES_APPENDED.json').exists():time.sleep(30)
    for fit in fits:
        name='sem_coarse_'+fit['id']
        if not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,coarse,arms(fit),[0],chunk=2,arm_chunk=64)
    summaries=[]
    for block in plan['blocks']:
        group=[f for f in fits if f['block']==block['name']]
        if not group:continue
        completed=[wait('sem_coarse_'+f['id']) for f in group];choices=choose(completed);name='sem_replay_'+block['name'];summaries.append(put(name,replay,choices,[0],chunk=4))
    if not summaries:
        atomic(DEST/'NO_COMPETITIVE_CANDIDATES.json',dict(status='COMPLETE',time=stamp(),scope='No corrected-span readout passed prespecified effect-size/AUROC/AP criteria; no repair candidate can be claimed.'));return
    lock=DEST/'PARENT_LOCK.json'
    if not lock.exists():atomic(lock,dict(status='FROZEN',time=stamp(),parents=choose_parents(summaries),test_not_used=True,source_stages=[s['stage'] for s in summaries]))
    parents=read(lock)['parents'];refined=refined_arms(parents)
    refined_path=DEST/'REFINE_ARMS.json'
    if not refined_path.exists():atomic(refined_path,refined)
    panel=read(VOUT/'global_funnel/REFINE_PANEL.json');refine=put('sem_global_refine',panel,read(refined_path),[0]);pool=selected(refine,16)
    rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='validation'];validation=put('validation_semantic',rows,pool,[0,1,2],chunk=4)
    records=[r for r in validation['summaries'] if r['displacement_max_m']>1e-8];safe=[r for r in records if r['safe_net']]
    if not records:atomic(DEST/'NO_ACTIVE_VALIDATED_CANDIDATE.json',dict(status='COMPLETE',time=stamp()));return
    roles=dict(pdms_priority=max(records,key=lambda r:r['mean_delta_pdms']),safety_priority=max(safe,key=lambda r:r['mean_delta_pdms']) if safe else min(records,key=lambda r:(sum(max(r[k],0) for k in ['collision_net','offroad_net','zero_net']),-r['mean_delta_pdms'])))
    atomic(DEST/'FINAL_LOCK.json',dict(status='FROZEN_BEFORE_SEMANTIC_TEST',time=stamp(),roles=roles,safety_eligible=bool(safe),safety_fallback_diagnostic_only=not bool(safe),primary_study_selection_unchanged=True,test_is_locked_reevaluation=True))
    from vlm_final_driver import null
    finalparents=list({r['arm']['id']:r['arm'] for r in roles.values()}.values());controls=[null(p,k,j) for p in finalparents for k,j in [('reverse',0),('haar_rotation',0),('haar_rotation',1),('haar_rotation',2)]]
    atomic(DEST/'TEST_LOCK.json',dict(status='FROZEN_BEFORE_TEST',time=stamp(),parents=finalparents,controls=controls,roles={k:r['arm']['id'] for k,r in roles.items()},seeds=[0,1,2,3,4],correct_joint_family='Holm across primary-study and corrected-span global role contrasts; report component diagnostics separately'))
    test=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');put('final_test_semantic',test,finalparents+controls,[0,1,2,3,4],chunk=2)
    atomic(DEST/'INFERENCE_COMPLETE.json',dict(status='PASS',time=stamp(),test_cases=len(test),test_seeds=5,full_residual_grid_progress_must_be_reported_separately=True))
if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(VOUT/'failures/semantic_repair_controller.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
