"""Freeze the candidate-repair search and append its first exploration-only screen."""
from common import *
import numpy as np
from collections import Counter
from candidate_repair_fit import OUT
from candidate_repair_queue import stage

RUN='candidate_repair_20261016_v1'

def arm(spec,method,alpha=.5,calibration=None,gate='none',cap=.05,**extra):
    c=spec['candidate']
    a=dict(fit=spec['id'],candidate=c['id'],route=c['route'],step=c['step'],layer=c['layer'],token=c['token'],r=spec['rank']['effective_r'],
        space=spec['kind'],method=method,alpha=alpha,calibration=calibration or ('n' if c['route']=='r1' else 'p'),gate=gate,cap=cap,**extra)
    a['id']='cr_'+digest(a)[:16];return a

def main():
    setup('candidate_repair/prepare');fits=read(OUT/'FITS_READY.json')['fits'];arms=[]
    for spec in fits:
        if spec['kind']=='candidate':
            calibrations=['n'] if spec['candidate']['route']=='r1' else ['p','n']
            for cal in calibrations:
                for method in ['mean','boundary','contract','ot']:
                    for alpha in [.1,.5,1.]:
                        for gate in ['none','risk99']:arms.append(arm(spec,method,alpha,cal,gate))
            if spec['candidate']['route']=='r2':
                for method in ['linear','mlp','local','linear_replay','mlp_replay']:
                    for alpha in [.1,.5,1.]:arms.append(arm(spec,method,alpha))
            for method in ['mean','boundary','ot']:
                for cap in [.01,.1]:arms.append(arm(spec,method,.5,cap=cap))
            arms.append(arm(spec,'reverse',control=True))
        else:
            for method in ['mean','contract','ot']:arms.append(arm(spec,method,.5,control=True))
    for spec in [s for s in fits if s['kind']=='candidate' and s['candidate']['id'] in ['r1_pooled_centered_unequal_region0','r2_pooled_centered_unequal_region9']]:
        for rep in [0,1,2]:
            rng=np.random.default_rng(20261016+rep+int(digest(spec['id'])[:6],16));u=rng.standard_normal(len(np.load(ROOT/spec['fit_path'])['center']))
            arms.append(arm(spec,'random_direction',control=True,random_direction=u.tolist(),construction_seed=rep))
    assert len({a['id'] for a in arms})==len(arms)
    atomic(OUT/'coarse_arms.json',arms)
    # Enrichment is declared; selection uses inverse sampling weights for natural PDMS.
    population=read(ROOT/'manifests/natural_s0.json');train=[r for r in population if r['subset']=='exploration'];panel=[]
    for quality,n in [('failure',1850),('high_quality',1200),('intermediate',600)]:
        eligible=sorted([r for r in train if r['quality']==quality],key=lambda r:digest(dict(token=r['token'],candidate_repair_screen=20261016)))
        panel.extend(eligible[:n])
    panel.sort(key=lambda r:r['global_index']);atomic(OUT/'coarse_panel.json',panel)
    # Smoke spans every leader, 512-D output, all mechanisms, calibrations and controls.
    smoke=[]
    for spec in [s for s in fits if s['kind']=='candidate']:
        smoke.append(next(a for a in arms if a['fit']==spec['id'] and a['method']=='mean' and a['alpha']==.5 and a['gate']=='none' and a['cap']==.05))
    for method in ['boundary','contract','ot','linear','mlp','local','linear_replay','mlp_replay','random_direction','reverse']:
        smoke.append(next(a for a in arms if a['method']==method and a['alpha']==.5))
    smoke.append(next(a for a in arms if a['gate']=='risk99'))
    smoke=list({a['id']:a for a in smoke}.values());atomic(OUT/'smoke_arms.json',smoke)
    tasks=stage(ROOT/'runs'/RUN,'coarse',panel,arms,[0],chunk=2)
    protocol=dict(status='FROZEN',time=stamp(),run=RUN,candidates=10,coarse_arms=len(arms),coarse_cases=len(panel),coarse_counts=dict(Counter(r['quality'] for r in panel)),
        methods=sorted({a['method'] for a in arms}),alphas=[.1,.5,1.],caps=[.01,.05,.1],natural_calibration=True,source_subset='exploration only',
        gate_quantiles=[.95,.99,.995],benefit_gate_fit='exploration repair outcomes only, natural coordinates, population weighted',
        next_stages=['expanded successful replay screen','full validation','matched null and dimension controls','locked final test'],
        validation_cases=17475,validation_seeds=[0,1,2],test_seeds=[0,1,2,3,4],final_roles=['route1_safety','route1_pdms','route2_safety','route2_pdms','global_safety','global_pdms'],
        safety_constraints=['net_collision<=0','net_offroad<=0','net_zero<=0','mean_delta_pdms>=0'],ttc_and_total_failure='reported separately',
        repair_ge70=True,complete_repair_gt90=True,original_high_damage=True,all_component_scores=True,session_bootstrap=True,
        prior_navtest_results_already_known=True,test_label='locked second-round evaluation on reused navtest, not a newly untouched test set',
        no_test_driven_fitting_or_adaptation=True,resources=dict(nodes=2,gpus_per_node=16,retain_until_all_heavy_work_done=True,max_minutes=720,reserved_minutes=0),
        scope='All confirmed expanded regions; no new dimension grid or model representation recollection',initial_tasks=tasks)
    atomic(OUT/'PROTOCOL.json',protocol);print(json.dumps(protocol),flush=True)

if __name__=='__main__':main()
