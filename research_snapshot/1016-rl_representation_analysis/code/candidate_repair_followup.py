"""Prespecified train/validation progression for expanded-candidate repair experiments."""
from common import *
import argparse
import copy
from collections import Counter
import numpy as np
import subprocess
from candidate_repair_fit import OUT
from candidate_repair_analysis import summarize,safety
from candidate_repair_queue import stage
from paired_observation import save_arrays

RUN='candidate_repair_20261016_v1'

def new_id(a):
    a=dict(a);a.pop('id',None);a['id']='cr_'+digest(a)[:16];return a

def summarized(name):
    p=OUT/'analysis'/name/'SUMMARY.json'
    if not p.exists():summarize(ROOT/'runs'/RUN,name)
    safety(name)
    return read(p)

def nets(summary,name):
    safe={r['arm_id']:r for r in read(OUT/'analysis'/name/'SAFETY.json')['records']}
    result=[]
    for row in summary['summaries']:
        net={k:sum(s[k]['net'] for s in safe[row['arm']['id']]['by_seed']) for k in ['collision','offroad','zero','ttc']}
        result.append(dict(summary=row,net=net,added=sum(max(net[k],0) for k in ['collision','offroad','zero'])))
    return result

def benefit(parent,coarse):
    path=OUT/'gates'/(parent['id']+'.npz')
    if path.exists():return str(path.relative_to(ROOT))
    source=OUT/'analysis/coarse'
    if parent['calibration']=='q':source=OUT/'analysis/quality_screen'
    rows=read(source/'rows.json');arms=read(source/'arms.json');index=1+next(i for i,a in enumerate(arms) if a['id']==parent['id'])
    scores=np.load(source/'scores.npy',mmap_mode='r');target=scores[0,:,index,0]-scores[0,:,0,0]
    spec=read(OUT/'fits'/(parent['fit']+'.json'));assert sha(ROOT/spec['coordinate_path'])==spec['coordinate_sha256']
    with np.load(ROOT/spec['fit_path']) as f:position={int(n):i for i,n in enumerate(f['native_indices'])}
    coordinates=np.load(ROOT/spec['coordinate_path'],mmap_mode='r');x=np.asarray(coordinates[[position[r['global_index']] for r in rows]],dtype=np.float64)
    mean=x.mean(0);scale=np.maximum(x.std(0),1e-6);z=(x-mean)/scale
    pop=Counter(r['quality'] for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration');sample=Counter(r['quality'] for r in rows)
    weight=np.array([pop[r['quality']]/sample[r['quality']] for r in rows]);weight/=weight.mean()
    intercept=float(np.average(target,weights=weight));coef=np.linalg.solve(z.T@(weight[:,None]*z)+.1*len(z)*np.eye(z.shape[1]),z.T@(weight*(target-intercept)))
    save_arrays(path,mean=mean,scale=scale,weight=coef,intercept=intercept)
    atomic(path.with_suffix('.json'),dict(status='FROZEN',time=stamp(),sha256=sha(path),fit='exploration outcomes only',parent=parent,rows=len(rows),ridge=.1,
        inference_input='native pre-intervention coordinates only',uses_gt_or_pdms_at_inference=False,weighted_training_mean_delta=intercept))
    return str(path.relative_to(ROOT))

def probe(name,arms):
    path=OUT/'planned_stages'/(name+'_arms.json');path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert read(path)==arms
    else:atomic(path,arms)
    proof=OUT/'probes'/(name+'.json')
    if not proof.exists():
        with (ROOT/'provenance'/('candidate_repair_probe_'+name+'.log')).open('w') as log:
            subprocess.run([sys.executable,'-B',str(ROOT/'code/candidate_repair_probe.py'),'--name',name,'--arms',str(path)],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    assert read(proof)['arms_sha256']==sha(path)

def replay():
    from candidate_repair_monitor import wait
    wait('quality_screen')
    summary=summarized('coarse');entries=nets(summary,'coarse')
    quality=summarized('quality_screen');entries+=nets(quality,'quality_screen')
    pool=[r for r in entries if r['summary']['arm']['space']=='candidate' and not r['summary']['arm'].get('control') and r['summary']['arm']['gate']=='none']
    parents={}
    for candidate in read(OUT/'CANDIDATES.json')['candidates']:
        group=[r for r in pool if r['summary']['arm']['candidate']==candidate['id']]
        pdms=max(group,key=lambda r:r['summary']['population_weighted_screen_delta'])
        safe=min(group,key=lambda r:(r['added'],r['summary']['high_damage_to_failure_rate'],-r['summary']['population_weighted_screen_delta']))
        for item in [pdms,safe]:parents[item['summary']['arm']['id']]=item['summary']['arm']
        used={p['method'] for p in parents.values() if p['candidate']==candidate['id']}
        other=[r for r in group if r['summary']['arm']['method'] not in used]
        if other:
            row=max(other,key=lambda r:r['summary']['population_weighted_screen_delta']);parents[row['summary']['arm']['id']]=row['summary']['arm']
    # Ensure no tested mechanism is discarded solely because another family leads the screen.
    for method in ['mean','boundary','contract','ot','linear','mlp','local','linear_replay','mlp_replay','quality_gradient']:
        group=[r for r in pool if r['summary']['arm'].get('mechanism',r['summary']['arm']['method'])==method]
        if group:
            row=max(group,key=lambda r:r['summary']['population_weighted_screen_delta']);parents[row['summary']['arm']['id']]=row['summary']['arm']
    chosen=[]
    for parent in parents.values():
        chosen.append(parent)
        for gate in ['risk95','risk99','risk995']:chosen.append(new_id(dict(parent,gate=gate,parent=parent['id'])))
        gp=benefit(parent,summary)
        for threshold in [0.,.001]:chosen.append(new_id(dict(parent,gate='benefit',benefit_path=gp,benefit_threshold=threshold,parent=parent['id'])))
    chosen=list({a['id']:a for a in chosen}.values())
    atomic(OUT/'REPLAY_SELECTION.json',dict(status='FROZEN_BEFORE_REPLAY',time=stamp(),rule='per-region PDMS, least observed added safety and damage, distinct mechanism; then best representative of every method; only exploration',parents=list(parents.values()),arms=chosen,validation_used=False))
    probe('replay',chosen)
    count=stage(ROOT/'runs'/RUN,'replay',read(ROOT/'repair_v1/screen.json'),chosen,[0],chunk=4)
    print(json.dumps(dict(event='REPLAY_APPENDED',tasks=count,arms=len(chosen))),flush=True)

def legacy():
    lock=read(ROOT/'repair_v1/TEST_LOCK.json');out=[]
    for role in ['safety_priority','pdms_priority']:
        a=lock['choices'][role]['summary']['arm']
        out.append(dict(id='legacy_'+role,method='legacy',legacy_arm=a,route='legacy',candidate='legacy',cap=a['cap'],control=True))
    for factor in [1.005,1.02]:out.append(dict(id='scale_'+str(factor),method='trajectory_scale',factor=factor,cap=0.,route='control',candidate='scale',control=True))
    return out

def validation():
    summary=summarized('replay');rows=nets(summary,'replay');chosen={}
    for candidate in read(OUT/'CANDIDATES.json')['candidates']:
        group=[r for r in rows if r['summary']['arm']['candidate']==candidate['id']]
        pdms=max(group,key=lambda r:r['summary']['population_weighted_screen_delta'])
        eligible=[r for r in group if r['added']==0 and r['summary']['population_weighted_screen_delta']>=0]
        safe=max(eligible,key=lambda r:r['summary']['population_weighted_screen_delta']) if eligible else min(group,key=lambda r:(r['added'],r['summary']['high_damage_to_failure_rate'],-r['summary']['population_weighted_screen_delta']))
        for entry in [pdms,safe]:chosen[entry['summary']['arm']['id']]=entry['summary']['arm']
    for method in ['mean','boundary','contract','ot','linear','mlp','local','linear_replay','mlp_replay','quality_gradient']:
        group=[r for r in rows if r['summary']['arm'].get('mechanism',r['summary']['arm']['method'])==method]
        if group:
            entry=max(group,key=lambda r:r['summary']['population_weighted_screen_delta']);chosen[entry['summary']['arm']['id']]=entry['summary']['arm']
    # Explore a few complementary sites before full validation; never tune combinations on test.
    combos=[];genuine=[r for r in rows if r['summary']['arm']['cap']==.05]
    leads=[]
    for route in ['r1','r2']:
        group=[r for r in genuine if r['summary']['arm']['route']==route]
        leads.append(max(group,key=lambda r:r['summary']['population_weighted_screen_delta'])['summary']['arm'])
    candidates=sorted(genuine,key=lambda r:r['summary']['population_weighted_screen_delta'],reverse=True)
    pairs=[leads]
    for route in ['r1','r2']:
        pool=[r['summary']['arm'] for r in candidates if r['summary']['arm']['route']==route]
        first=pool[0];second=next((a for a in pool[1:] if (a['step'],a['layer'],a['token'])!=(first['step'],first['layer'],first['token'])),None)
        if second:pairs.append([first,second])
    for pair in pairs:
        for strength in [.5,1.]:
            parts=[dict(a,alpha=a['alpha']*strength,cap=.05) for a in pair]
            combos.append(new_id(dict(method='combination',components=parts,cap=.05,route='mixed' if len({a['route'] for a in pair})>1 else pair[0]['route'],candidate='combination',budget='per-token cross-site relative L2 <= .05',control=False)))
    atomic(OUT/'VALIDATION_SELECTION.json',dict(status='FROZEN_BEFORE_VALIDATION',time=stamp(),single_arms=list(chosen.values()),combinations=combos,validation_used=False))
    val_arms=list(chosen.values())+legacy();probe('validation',val_arms)
    count=stage(ROOT/'runs'/RUN,'validation',read(ROOT/'repair_v1/validation.json'),val_arms,[0,1,2],chunk=8)
    if combos:
        probe('combination_screen',combos)
        stage(ROOT/'runs'/RUN,'combination_screen',read(OUT/'coarse_panel.json'),combos,[0],chunk=8)
    print(json.dumps(dict(event='VALIDATION_APPENDED',tasks=count,arms=len(val_arms),combination_arms=len(combos))),flush=True)

def combinations():
    result=summarized('combination_screen');rows=nets(result,'combination_screen')
    # Both strengths are retained, with matched individual components at the same global budget.
    selected=read(ROOT/'runs'/RUN/'stages/combination_screen/arms.json');singles={}
    for a in selected:
        for component in a['components']:
            s=new_id(dict(component,cap=.05));singles[s['id']]=s
    arms=selected+list(singles.values());probe('validation_combinations',arms)
    count=stage(ROOT/'runs'/RUN,'validation_combinations',read(ROOT/'repair_v1/validation.json'),arms,[0,1,2],chunk=8)
    atomic(OUT/'COMBINATION_VALIDATION_SELECTION.json',dict(status='FROZEN',time=stamp(),arms=arms,rule='all six prespecified exploratory compositions and matched single components, no validation adaptation'))
    print(json.dumps(dict(event='COMBINATION_VALIDATION_APPENDED',tasks=count,arms=len(arms))),flush=True)

def finalists():
    from candidate_repair_monitor import wait
    wait('validation_temporal')
    entries=[]
    for name in ['validation','validation_combinations','validation_temporal']:
        summary=summarized(name)
        for r in nets(summary,name):
            if not r['summary']['arm'].get('control'):entries.append(dict(r,stage=name))
    unique={r['summary']['arm']['id']:r for r in entries};entries=list(unique.values());choices={}
    for label,route in [('route1','r1'),('route2','r2'),('global',None)]:
        group=[r for r in entries if route is None or r['summary']['arm']['route']==route]
        pdms=max(group,key=lambda r:r['summary']['mean_delta_pdms'])
        eligible=[r for r in group if r['added']==0 and r['summary']['mean_delta_pdms']>=0]
        safe=max(eligible,key=lambda r:r['summary']['mean_delta_pdms']) if eligible else min(group,key=lambda r:(r['added'],r['net']['collision'],r['net']['offroad'],r['net']['zero'],r['summary']['high_damage_to_failure_rate'],-r['summary']['mean_delta_pdms']))
        choices[label+'_safety']=dict(safe,safety_eligible=bool(eligible))
        choices[label+'_pdms']=pdms
    arms=list({r['summary']['arm']['id']:r['summary']['arm'] for r in choices.values()}.values())
    lock=OUT/'BEHAVIOR_SELECTION_LOCK.json';assert not lock.exists()
    atomic(lock,dict(status='LOCKED_BEFORE_SECOND_ROUND_TEST',time=stamp(),choices=choices,arms=arms,
        source_summaries={name:sha(OUT/'analysis'/name/'SUMMARY.json') for name in ['validation','validation_combinations','validation_temporal']},
        test_results_from_this_round_accessed=False,prior_round_test_already_used=True,safety_constraints=read(OUT/'PROTOCOL.json')['safety_constraints']))
    controls=[]
    # Fully matched pre-cap norm, location, gate, alpha and native RNG. The three Haar seeds are controls, not cases.
    parent_map={choices[k]['summary']['arm']['id']:choices[k]['summary']['arm'] for k in ['global_safety','global_pdms']}
    for candidate in ['r1_pooled_centered_unequal_region0','r2_pooled_centered_unequal_region9']:
        original=next(c for c in read(OUT/'CANDIDATES.json')['candidates'] if c['id']==candidate)
        group=[r for r in entries if r['summary']['arm'].get('candidate')==candidate and 'components' not in r['summary']['arm'] and r['summary']['arm'].get('step')==original['step'] and r['summary']['arm'].get('calibration') in ['n','p','q']]
        best=max(group,key=lambda r:r['summary']['mean_delta_pdms'])['summary']['arm'];parent_map[best['id']]=best
    parents=list(parent_map.values())
    for parent in parents:
        parts=parent.get('components',[parent])
        for kind in ['reverse','haar0','haar1','haar2']:
            modified=[]
            for part in parts:
                a=dict(part,control=True,control_kind='reverse' if kind=='reverse' else 'haar_rotation')
                if kind.startswith('haar'):a['alternative_basis']=part['candidate']+'__haar'+kind[-1]
                modified.append(new_id(a))
            a=new_id(dict(parent,components=modified,control=True,control_kind=kind,parent=parent['id'])) if 'components' in parent else modified[0]
            a['parent']=parent['id'];controls.append(a)
        if parent.get('candidate') in ['r1_pooled_centered_unequal_region0','r2_pooled_centered_unequal_region9'] and 'components' not in parent and parent.get('calibration') in ['n','p','q'] and parent['step']==next(c['step'] for c in read(OUT/'CANDIDATES.json')['candidates'] if c['id']==parent['candidate']):
            for kind in ['equal_mean','full_mean']:
                alternative=parent['candidate']+('__equal0' if kind=='equal_mean' else '__full0')+('__quality' if parent.get('calibration')=='q' else '')
                a=new_id(dict(parent,control=True,control_kind=kind,alternative_basis=alternative,parent=parent['id'],
                    control_scope='replace direction by alternative-space continuous ridge when calibration=q, otherwise source mean gap; preserve parent dynamic pre-cap norm and gate; not a full OT/MLP operator refit'))
                controls.append(a)
    atomic(OUT/'MATCHED_CONTROLS.json',dict(status='FROZEN',time=stamp(),parent_selection_lock_sha256=sha(lock),arms=controls,selection_changed=False))
    probe('validation_controls',controls)
    count=stage(ROOT/'runs'/RUN,'validation_controls',read(ROOT/'repair_v1/validation.json'),controls,[0,1,2],chunk=8)
    print(json.dumps(dict(event='FINALISTS_LOCKED_CONTROLS_APPENDED',choices={k:dict(id=v['summary']['arm']['id'],delta=v['summary']['mean_delta_pdms'],net=v['net']) for k,v in choices.items()},tasks=count,control_arms=len(controls))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['replay','validation','combinations','finalists']);args=p.parse_args()
    setup('candidate_repair/followup/'+args.phase);compatibility()
    globals()[args.phase]()
