"""Corrected-span repair funnel, including inactive fits and ungated diagnostics."""
from common import *
from vlm_semantic import SEM
from vlm_core import VOUT
from vlm_selection import block_candidates,confirm,finite
from vlm_fits import make
from vlm_funnel import arms
from vlm_replay import choose
from vlm_global_funnel_v5 import choose_parents,selected,refined_arms,combinations
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
    assert choices, 'An inactive pool must not create an empty GPU stage'
    if not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,rows,choices,seeds,chunk=chunk,arm_chunk=64)
    return wait(name)

def no_candidates(reason):
    atomic(DEST/'NO_COMPETITIVE_CANDIDATES.json',dict(status='COMPLETE',time=stamp(),reason=reason,
        no_positive_repair_claim=True,full_grid_completion_reported_separately=True))

def main():
    setup('vlm_semantic_v2/repair_v3');from threadpoolctl import threadpool_limits
    DEST.mkdir(exist_ok=True)
    while not (SEM/'ANALYSIS_EXECUTION.json').exists():time.sleep(30)
    while any(len(list((SEM/kind/'receipts').glob('*.json')))!=64 for kind in ['rapid','scan']):time.sleep(30)
    plan=read(SEM/'PIVOT_PLAN.json');coarse=read(VOUT/'development/COARSE_PANEL.json');replay=read(VOUT/'replay/PANEL.json');fits=[]
    for block in plan['blocks']:
        path=DEST/'selections'/(block['name']+'.json')
        if not path.exists():
            selection=block_candidates(block['name'],analysis_root=SEM);assert selection is not None
            from vlm_residual_candidates import select
            extras=select(block['name'],SEM)
            selection['selected']=list({digest(dict(cell=r['cell'],config=r['config'],centering=r['centering'])):r for r in selection['selected']+extras}.values())
            selection['selected']=[r for r in selection['selected'] if finite(r['metrics']['auc'])>=.6 and finite(r['metrics']['standardized_gap'])>=.2 and finite(r['metrics']['weighted_ap'])>finite(r['metrics']['class_prevalence'])]
            selection['all_64_full_residual_grids_completed_before_selection']=True
            atomic(path,selection)
        for spec in read(path)['selected']:
            try:
                with threadpool_limits(limits=2):fit=make(spec);confirmation=confirm(fit)
            except AssertionError as error:
                atomic(DEST/'rejected_fits'/(digest(spec)[:20]+'.json'),dict(status='INELIGIBLE_REFIT',time=stamp(),spec=spec,reason=repr(error)));continue
            fits.append(fit);atomic(DEST/'fits'/(fit['id']+'.json'),dict(fit=fit,confirmation=confirmation))
    if not fits:no_candidates('No corrected-span readout passed the prespecified effect-size/AUROC/AP and valid-refit criteria.');return
    while not (VOUT/'final/PRIMARY_STAGES_APPENDED.json').exists():time.sleep(30)
    for fit in fits:
        name='sem_coarse_'+fit['id']
        if not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,coarse,arms(fit),[0],chunk=2,arm_chunk=64)
    summaries=[]
    for block in plan['blocks']:
        group=[f for f in fits if f['block']==block['name']]
        if not group:continue
        completed=[wait('sem_coarse_'+f['id']) for f in group];choices=choose(completed)
        if choices:summaries.append(put('sem_replay_'+block['name'],replay,choices,[0],chunk=4))
    if not summaries:no_candidates('No eligible corrected-span coarse arm.');return
    lock=DEST/'PARENT_LOCK.json'
    if not lock.exists():atomic(lock,dict(status='FROZEN',time=stamp(),parents=choose_parents(summaries),test_not_used=True,source_stages=[s['stage'] for s in summaries]))
    parents=read(lock)['parents']
    if not parents:no_candidates('All tested corrected-span operators remained trajectory-identical to Base.');return
    refined_path=DEST/'REFINE_ARMS.json'
    if not refined_path.exists():
        with threadpool_limits(limits=2):atomic(refined_path,refined_arms(parents))
    panel=read(VOUT/'global_funnel/REFINE_PANEL.json');refine=put('sem_global_refine',panel,read(refined_path),[0]);pool=selected(refine,16)
    if not pool:no_candidates('No active corrected-span refined candidate.');return
    # Same fresh 3650-case replay and component combinations as the main funnel.
    broad=read(ROOT/'candidate_repair_v1/analysis/coarse/rows.json');broad_result=put('sem_global_replay',broad,pool,[0],chunk=4)
    pool=selected(broad_result,16);combo=combinations(broad_result)
    if combo:
        screened=put('sem_combination_screen',panel,combo,[0]);combo_pool=selected(screened,4)
        if combo_pool:pool+=selected(put('sem_combination_replay',broad,combo_pool,[0],chunk=4),4)
    for arm in list(pool):
        if arm['method']=='combination' or arm.get('gate')=='none':continue
        a=dict(arm,gate='none');a.pop('gate_threshold',None);a.pop('id');a['ungated_parent']=arm['id'];a['id']='sem_ungated_'+digest(a)[:16];pool.append(a)
    pool=list({a['id']:a for a in pool}.values())
    rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='validation'];validation=put('validation_semantic',rows,pool,[0,1,2],chunk=4)
    records=[r for r in validation['summaries'] if r['displacement_max_m']>1e-8];safe=[r for r in records if r['safe_net']]
    if not records:no_candidates('No active corrected-span candidate on full session validation.');return
    roles=dict(pdms_priority=max(records,key=lambda r:r['mean_delta_pdms']),safety_priority=max(safe,key=lambda r:r['mean_delta_pdms']) if safe else min(records,key=lambda r:(sum(max(r[k],0) for k in ['collision_net','offroad_net','zero_net']),-r['mean_delta_pdms'])))
    atomic(DEST/'FINAL_LOCK.json',dict(status='FROZEN_BEFORE_SEMANTIC_TEST',time=stamp(),roles=roles,safety_eligible=bool(safe),safety_fallback_diagnostic_only=not bool(safe),primary_study_selection_unchanged=True,test_is_locked_reevaluation=True))
    from vlm_final_driver import null
    finalparents=list({r['arm']['id']:r['arm'] for r in roles.values()}.values());controls=[null(p,k,j) for p in finalparents for k,j in [('reverse',0),('haar_rotation',0),('haar_rotation',1),('haar_rotation',2)]]
    atomic(DEST/'TEST_LOCK.json',dict(status='FROZEN_BEFORE_TEST',time=stamp(),parents=finalparents,controls=controls,roles={k:r['arm']['id'] for k,r in roles.items()},seeds=[0,1,2,3,4],correct_joint_family='Holm across primary-study and corrected-span global role contrasts; component diagnostics separately'))
    if not (DEST/'ENGINEERING_PASS.json').exists():
        import subprocess
        while len(read(BASE/'tasks.json'))!=len(list((BASE/'receipts').glob('*.json'))):time.sleep(10)
        atomic(DEST/'ENGINEERING_REQUEST.json',dict(arms=finalparents+controls))
        env=dict(os.environ,CUDA_VISIBLE_DEVICES='0')
        for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
        with (DEST/'engineering.log').open('a') as stream:subprocess.run([sys.executable,'-u','-B',str(ROOT/'code/vlm_semantic_engineering.py')],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        assert read(DEST/'ENGINEERING_PASS.json')['status']=='PASS'
    test=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');put('final_test_semantic',test,finalparents+controls,[0,1,2,3,4],chunk=2)
    atomic(DEST/'INFERENCE_COMPLETE.json',dict(status='PASS',time=stamp(),test_cases=len(test),test_seeds=5,full_residual_grid_progress_must_be_reported_separately=True))

if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(VOUT/'failures/semantic_repair_controller_v3.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
