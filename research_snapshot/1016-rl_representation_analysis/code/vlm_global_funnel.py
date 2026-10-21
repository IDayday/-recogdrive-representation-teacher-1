"""Training-only global funnel: gate/strength refinement, broad replay, combinations and full validation."""
from common import *
import argparse
import numpy as np
from collections import Counter
from vlm_core import VOUT
from vlm_results import summarize
from vlm_scan import save_npz
from vlm_repair_queue_v2 import stage
from repair_queue_v2 import atomic_unique as atomic

RUN='vlm_repair_20261016_v2';BASE=ROOT/'runs'/RUN;G=VOUT/'global_funnel'

def component(arm):
    if arm['method']=='combination':return 'combination'
    b=arm['block'];return 'vision' if b.startswith('vision') else 'bridge' if b.startswith('bridge') else 'interface' if b.startswith('interface') else 'language'

def wait_stage(name):
    while True:
        if (BASE/'stages'/name/'PROTOCOL.json').exists():
            result=summarize(BASE,name)
            if result is not None:return result
        failures=list((BASE/'failures').glob('*.json'))+list(VOUT.glob('**/failures/*.json'))
        if failures:raise RuntimeError('Original failure '+str(failures[0]))
        time.sleep(30)

def source_record(summary,record):return dict(arm=record['arm'],metrics={k:v for k,v in record.items() if k!='arm'},stage=summary['stage'])

def unique(records):return list({r['arm']['id']:r for r in records}.values())

def choose_parents(summaries):
    records=[source_record(s,r) for s in summaries for r in s['summaries'] if r['activation_rate']>0 and r['displacement_max_m']>1e-8];out=[]
    for method in sorted({r['arm']['method'] for r in records}):
        group=[r for r in records if r['arm']['method']==method]
        out.append(max(group,key=lambda r:r['metrics']['population_weighted_delta_pdms']))
        out.append(max(group,key=lambda r:r['metrics']['oracle_failure_gate_delta_pdms']))
    for c in ['vision','bridge','language','interface']:
        group=[r for r in records if component(r['arm'])==c]
        if group:
            out.append(max(group,key=lambda r:r['metrics']['population_weighted_delta_pdms']))
            out.append(max(group,key=lambda r:r['metrics']['oracle_failure_gate_delta_pdms']))
    return unique(out)

def fresh_panel():
    excluded={r['token'] for p in [VOUT/'development/COARSE_PANEL.json',VOUT/'replay/PANEL.json'] for r in read(p)}
    rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration' and r['token'] not in excluded];out=[]
    for label,n in [('failure',256),('high_quality',128),('intermediate',128)]:
        group=sorted([r for r in rows if r['quality']==label],key=lambda r:digest(dict(token=r['token'],vlm_refine_root=20261016)));out.extend(group[:n])
    assert len(out)==512;return out

def gate_fit(parent):
    arm=parent['arm'];existing=G/'gates'/(arm['id']+'.json')
    if existing.exists():
        previous=read(existing);assert previous['parent']==parent and sha(ROOT/previous['path'])==previous['sha256'];return previous
    folder=VOUT/'analysis'/parent['stage'];rows=read(folder/'rows.json');arms=read(folder/'arms.json');i=next(i+1 for i,a in enumerate(arms) if a['id']==arm['id']);scores=np.load(folder/'scores.npy',mmap_mode='r');target=scores[0,:,i,0]-scores[0,:,0,0]
    with np.load(ROOT/arm['fit_path']) as f:arrays={k:np.array(f[k]) for k in f.files}
    original=read((ROOT/arm['fit_path']).with_suffix('.json'));proof=read(ROOT/original['cell_proof_path']);x=np.load(ROOT/proof['path'],mmap_mode='r');indices=[r['global_index'] for r in rows]
    z=(np.asarray(x[indices],dtype=np.float64)-arrays['center'])@arrays['basis'];pop=Counter(r['quality'] for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration');counts=Counter(r['quality'] for r in rows);weight=np.array([pop[r['quality']]/counts[r['quality']] for r in rows]);weight/=weight.mean()
    mu=np.average(z,axis=0,weights=weight);scale=np.maximum(np.sqrt(np.average((z-mu)**2,axis=0,weights=weight)),1e-6);standard=(z-mu)/scale
    intercept=float(np.average(target,weights=weight));w=np.linalg.solve(standard.T@(weight[:,None]*standard)+.5*len(z)*np.eye(z.shape[1]),standard.T@(weight*(target-intercept)))
    arrays.update(benefit_center=mu.astype('float32'),benefit_scale=scale.astype('float32'),benefit_weights=w.astype('float32'),benefit_intercept=np.array(intercept,dtype='float32'))
    metadata=read(ROOT/'manifests/natural_s0.json');q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy',mmap_mode='r');high=np.array([r['subset']=='exploration' for r in metadata])&(q>.9)&np.isfinite(x[:,0]);risk=(np.asarray(x[high],dtype=np.float64)-arrays['risk_center'])@arrays['risk_direction'];quantiles=np.quantile(risk,[.95,.99,.995]).tolist()
    path=G/'gates'/(arm['id']+'.npz');hashed=save_npz(path,**arrays);info=dict(status='PASS',time=stamp(),parent=parent,source_fit_sha256=arm['fit_sha256'],path=str(path.relative_to(ROOT)),sha256=hashed,fit_cases=len(rows),fit_subset='exploration repair outcomes only',risk_high_quantiles=dict(zip(['95','99','995'],quantiles)),input='natural upstream pooled coordinates; no score or GT at runtime',ridge=.5)
    atomic(path.with_suffix('.json'),info);return info

def refined_arms(parents):
    result=[]
    for parent in parents:
        arm=parent['arm'];gate=gate_fit(parent)
        for alpha_factor in [.5,1.,2.]:
            for cap_factor in [.5,1.,2.]:
                for kind in ['none','hard','soft','benefit']:
                    a=dict(arm,fit_path=gate['path'],fit_sha256=gate['sha256'],alpha=arm['alpha']*alpha_factor,cap=min(.2,arm['cap']*cap_factor),gate=kind,parent=arm['id'])
                    if kind in ['hard','soft']:a['gate_threshold']=gate['risk_high_quantiles']['99']
                    elif kind=='benefit':a['gate_threshold']=0.
                    a.pop('id');a['id']='vr_'+digest(a)[:18];result.append(a)
        for kind,threshold in [('hard',gate['risk_high_quantiles']['95']),('hard',gate['risk_high_quantiles']['995']),('benefit',.001)]:
            a=dict(arm,fit_path=gate['path'],fit_sha256=gate['sha256'],gate=kind,gate_threshold=threshold,parent=arm['id']);a.pop('id');a['id']='vr_'+digest(a)[:18];result.append(a)
    return list({a['id']:a for a in result}.values())

def selected(summary,maximum=32):
    records=summary['summaries'];out=[]
    for c in ['vision','bridge','language','interface','combination']:
        group=[r for r in records if component(r['arm'])==c and r['displacement_max_m']>1e-8]
        if not group:continue
        safe=[r for r in group if r['safe_net']]
        out.extend(sorted(group,key=lambda r:r['population_weighted_delta_pdms'],reverse=True)[:2]);out.extend(sorted(safe,key=lambda r:r['population_weighted_delta_pdms'],reverse=True)[:2]);out.append(max(group,key=lambda r:r['oracle_failure_gate_delta_pdms']))
    for method in sorted({r['arm']['method'] for r in records}):
        group=[r for r in records if r['arm']['method']==method];out.append(max(group,key=lambda r:r['population_weighted_delta_pdms']))
    # Protect operator families and component coverage before filling the budget.
    protected=[]
    for method in sorted({r['arm']['method'] for r in records}):
        group=[r for r in records if r['arm']['method']==method];protected.append(max(group,key=lambda r:r['population_weighted_delta_pdms']))
    for c in ['vision','bridge','language','interface','combination']:
        group=[r for r in records if component(r['arm'])==c and r['displacement_max_m']>1e-8]
        if not group:continue
        protected.append(max(group,key=lambda r:r['population_weighted_delta_pdms']))
        safe=[r for r in group if r['safe_net']]
        if safe:protected.append(max(safe,key=lambda r:r['population_weighted_delta_pdms']))
    result={r['arm']['id']:r['arm'] for r in protected};limit=max(maximum,len(result))
    for r in sorted(out,key=lambda r:(r['population_weighted_delta_pdms'],r['oracle_failure_gate_delta_pdms']),reverse=True):
        if len(result)>=limit:break
        result[r['arm']['id']]=r['arm']
    return list(result.values())


def combinations(summary):
    groups=[]
    for c in ['vision','bridge','language','interface']:
        rows=[r for r in summary['summaries'] if component(r['arm'])==c and r['displacement_max_m']>1e-8]
        if rows:groups.append(sorted(rows,key=lambda r:r['population_weighted_delta_pdms'],reverse=True)[:2])
    result=[]
    for i in range(len(groups)):
        for j in range(i+1,len(groups)):
            for a,b in [(groups[i][0],groups[j][0]),(groups[i][-1],groups[j][-1])]:
                for scale in [.5,1.]:
                    for cap in [.01,.05]:
                        parts=[dict(r['arm'],gate='none',alpha=r['arm']['alpha']*scale,cap=cap) for r in [a,b]]
                        arm=dict(method='combination',parts=parts,cap=cap,budget='per-site alpha and relative cap divided by sqrt(number of sites); recorded relative maximum, not an absolute physical group norm',ungated=True);arm['id']='vr_'+digest(arm)[:18];result.append(arm)
    return list({a['id']:a for a in result}.values())

def put(name,panel,arms,seeds,chunk=4):
    if not (BASE/'stages'/name/'PROTOCOL.json').exists():stage(BASE,name,panel,arms,seeds,chunk=chunk,arm_chunk=64)
    return wait_stage(name)

def main():
    setup('vlm_repair/global_funnel');G.mkdir(exist_ok=True)
    blocks=[b['name'] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']];summaries=[]
    for block in blocks:summaries.append(wait_stage('replay_'+block))
    # Canonical full residual coverage is a prerequisite for freezing the global pool.
    while True:
        canonical=read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical'];done={p.stem for p in (VOUT/'scan/receipts').glob('*.json')}
        if all(c['id'] in done for c in canonical):break
        atomic(G/'STATUS.json',dict(status='WAIT_CANONICAL_FULL_GRID',time=stamp(),canonical_done=sum(c['id'] in done for c in canonical),canonical_total=len(canonical)));time.sleep(30)
    for block in blocks:
        name='replay_residual_'+block
        lock=VOUT/'residual_development'/(block+'.json')
        while not lock.exists():time.sleep(10)
        if read(lock)['selected']:summaries.append(wait_stage(name))
    lock=G/'PARENT_LOCK.json'
    if not lock.exists():atomic(lock,dict(status='FROZEN',time=stamp(),parents=choose_parents(summaries),all_primary_blocks=62,canonical_full_grids_complete=True,source_stages=[s['stage'] for s in summaries],validation_test_not_used=True))
    parents=read(lock)['parents'];refine_path=G/'REFINE_ARMS.json'
    if not refine_path.exists():atomic(refine_path,refined_arms(parents))
    if not (G/'REFINE_PANEL.json').exists():atomic(G/'REFINE_PANEL.json',fresh_panel())
    refine=put('global_refine',read(G/'REFINE_PANEL.json'),read(refine_path),[0],chunk=2)
    broad_panel=read(ROOT/'candidate_repair_v1/analysis/coarse/rows.json');broad_arms=selected(refine,32)
    replay=put('global_replay',broad_panel,broad_arms,[0],chunk=4)
    combo_arms=combinations(replay)
    if combo_arms:
        combo=put('combination_screen',read(G/'REFINE_PANEL.json'),combo_arms,[0],chunk=2);combo_selected=selected(combo,4)
        if combo_selected:combo_replay=put('combination_replay',broad_panel,combo_selected,[0],chunk=4)
        else:combo_replay=None
    else:combo_replay=None
    candidates=selected(replay,16)
    if combo_replay:candidates+=selected(combo_replay,4)
    # Retain ungated counterparts for chosen learned/risk gates, separating recognition and operator.
    for arm in list(candidates):
        if arm['method']=='combination' or arm.get('gate')=='none':continue
        a=dict(arm,gate='none');a.pop('gate_threshold',None);a['id']='ungated_'+digest(a)[:16];a['ungated_parent']=arm['id'];candidates.append(a)
    candidates=list({a['id']:a for a in candidates}.values());rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='validation']
    validation_lock=G/'VALIDATION_LOCK.json'
    if not validation_lock.exists():atomic(validation_lock,dict(status='FROZEN',time=stamp(),arms=candidates,cases=len(rows),seeds=[0,1,2],safety_constraints=['net collision<=0','net offroad<=0','net zero<=0','mean PDMS>=0'],ttc_and_total_failure_reported_separately=True,final_test_not_used=True))
    validation=put('validation_main',rows,read(validation_lock)['arms'],[0,1,2],chunk=4)
    records=[r for r in validation['summaries'] if r['displacement_max_m']>1e-8];safe=[r for r in records if r['safe_net']];roles={}
    roles['pdms_priority']=max(records,key=lambda r:r['mean_delta_pdms'])
    roles['safety_priority']=max(safe,key=lambda r:r['mean_delta_pdms']) if safe else min(records,key=lambda r:(sum(max(r[k],0) for k in ['collision_net','offroad_net','zero_net']),-r['mean_delta_pdms']))
    diagnostics={}
    for c in ['vision','bridge','language','interface']:
        group=[r for r in records if component(r['arm'])==c]
        if group:diagnostics[c]=max(group,key=lambda r:r['mean_delta_pdms'])
    atomic(G/'FINAL_CANDIDATE_LOCK.json',dict(status='FROZEN_BEFORE_TEST',time=stamp(),roles=roles,component_diagnostics=diagnostics,safety_eligible=bool(safe),safety_fallback_diagnostic_only=not bool(safe),
        primary_family='global safety and PDMS roles versus Base; identical roles deduplicated',component_family='component representatives diagnostic versus Base, corrected separately',matched_nulls='reverse +3 independent Haar for distinct global role parents; component diagnostics without own nulls cannot independently establish direction-specific causality',
        candidate_test_reuses_navtest=True,no_test_result_used_for_new_selection=True,test_seeds=[0,1,2,3,4]))
    print('GLOBAL_FINAL_LOCK_READY',flush=True)
if __name__=='__main__':main()
