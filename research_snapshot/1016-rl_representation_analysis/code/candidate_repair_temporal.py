"""Train-only timing controls motivated by observed attenuation, preserving each original projector."""
from common import *
import numpy as np
from candidate_repair_fit import OUT,SCAN,project
from candidate_repair_prepare import arm
from candidate_repair_followup import probe,new_id,summarized,nets
from candidate_repair_queue import stage
from candidate_repair_monitor import wait
from repair_prepare import mapping
from paired_observation import save_arrays

RUN='candidate_repair_20261016_v1'

def prepare_fit(candidate,step):
    original=read(OUT/'fits'/(candidate['id']+'.json'));ident=candidate['id']+f'__time{step}';p=OUT/'fits'/(ident+'.npz')
    if p.exists():
        spec=read(p.with_suffix('.json'));assert sha(p)==spec['fit_sha256'];return spec
    with np.load(ROOT/original['fit_path']) as z:arrays={k:z[k] for k in z.files}
    b=arrays['b'];center=arrays['center'];meta=read(SCAN/'natural_metadata.json');exp=np.array([m['subset']=='exploration' for m in meta]);q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy')
    cell=f'r1_a-1_s{step}_l{candidate["layer"]}_t{candidate["token"]}';proof=read(SCAN/'CACHE_INDEX.json')['cells'][cell];path=SCAN/'cache'/(cell+'.npy');assert sha(path)==proof['sha256']
    x=np.load(path,mmap_mode='r');hi=project(x[exp&(q>.9)],b,center);lo=project(x[exp&(q<.7)],b,center)
    mh,ml,ch,cl,ot=mapping(hi,lo);gap=ml-mh;var=float(gap@((ch+cl)*.5)@gap);risk=gap/max(np.sqrt(var),1e-12);risk_high=(hi-mh)@risk
    source_delta=arrays['n_mh']-arrays['n_ml'];source_scale=arrays['n_scale']
    arrays.update(n_mh=mh,n_ml=ml,n_scale=np.sqrt(np.maximum(np.diag(ch),1e-6)),n_ot=ot,
        s_mh=source_delta,s_ml=np.zeros_like(source_delta),s_scale=source_scale,risk=risk,risk_origin=mh,
        risk95=np.quantile(risk_high,.95),risk99=np.quantile(risk_high,.99),risk995=np.quantile(risk_high,.995))
    save_arrays(p,**arrays)
    moved=dict(candidate,step=step)
    spec=dict(original,id=ident,candidate=moved,fit_path=str(p.relative_to(ROOT)),fit_sha256=sha(p),time=stamp(),
        coordinate_path=None,coordinate_sha256=None,source_projector_sha256=original['fit_sha256'],source_step=candidate['step'],target_step=step,
        native_target_cell=cell,native_target_sha256=proof['sha256'],projector_reused_exact=True,
        fit_subset='exploration only; source direction frozen, target natural calibration refit, no new SVD or collection')
    atomic(p.with_suffix('.json'),spec);return spec

def prepare():
    candidates=[c for c in read(OUT/'CANDIDATES.json')['candidates'] if c['route']=='r1'];fits={};arms=[]
    for c in candidates:
        for step in range(c['step'],5):fits[(c['id'],step)]=prepare_fit(c,step)
        for step in [c['step'],4]:
            spec=fits[(c['id'],step)];kind='original_norm_control' if step==c['step'] else 'late_transfer'
            for cap in [.01,.05]:
                for gate in ['none','risk99']:arms.append(arm(spec,'mean',1e6,'s',gate,cap,mechanism='fixed_direction_timing',timing_type=kind))
            for method in ['mean','contract']:
                for alpha in [.5,1.]:
                    for gate in ['none','risk99']:arms.append(arm(spec,method,alpha,'n',gate,.05,mechanism='target_time_calibration',timing_type=kind))
        for method,cal,alphas,caps in [('mean','s',[1e6],[.01,.05]),('mean','n',[.5,1.],[.05]),('contract','n',[.5,1.],[.05])]:
            for alpha in alphas:
                for cap in caps:
                    for gate in ['none','risk99']:
                        parts=[arm(fits[(c['id'],s)],method,alpha,cal,gate,cap) for s in range(c['step'],5)]
                        arms.append(new_id(dict(method='combination',components=parts,candidate=c['id'],route='r1',space='candidate',cap=cap,
                            mechanism='temporal_persistence',timing_type='persistent',source_step=c['step'],gate=gate,
                            total_budget='per-token cross-site relative L2 <= cap; each site cap/sqrt(number of sites)')))
    assert len(arms)==144 and len({a['id'] for a in arms})==144
    atomic(OUT/'TEMPORAL_ARMS.json',arms);atomic(OUT/'TEMPORAL_FITS_READY.json',dict(status='PASS',time=stamp(),fits=list(fits.values()),arms=len(arms)))
    probe('temporal_screen',arms)
    count=stage(ROOT/'runs'/RUN,'temporal_screen',read(OUT/'coarse_panel.json'),arms,[0],chunk=4)
    print(json.dumps(dict(event='TEMPORAL_SCREEN_APPENDED',tasks=count,arms=len(arms))),flush=True)

def validate():
    wait('temporal_screen');summary=summarized('temporal_screen');entries=nets(summary,'temporal_screen');all_arms=read(OUT/'TEMPORAL_ARMS.json');chosen={}
    for c in [c for c in read(OUT/'CANDIDATES.json')['candidates'] if c['route']=='r1']:
        for kind in ['late_transfer','persistent']:
            group=[r for r in entries if r['summary']['arm']['candidate']==c['id'] and r['summary']['arm']['timing_type']==kind]
            best=max(group,key=lambda r:r['summary']['population_weighted_screen_delta'])
            eligible=[r for r in group if r['added']==0 and r['summary']['population_weighted_screen_delta']>=0]
            safe=max(eligible,key=lambda r:r['summary']['population_weighted_screen_delta']) if eligible else min(group,key=lambda r:(r['added'],r['summary']['high_damage_to_failure_rate'],-r['summary']['population_weighted_screen_delta']))
            for row in [best,safe]:
                a=row['summary']['arm'];chosen[a['id']]=a
                if kind=='late_transfer':
                    reference=next(x for x in all_arms if x['candidate']==c['id'] and x['timing_type']=='original_norm_control' and x['method']==a['method'] and x['calibration']==a['calibration'] and x['alpha']==a['alpha'] and x['gate']==a['gate'] and x['cap']==a['cap'])
                    # A reference remains reportable and may be a genuine method in the common validation pool.
                    chosen[reference['id']]=reference
    arms=list(chosen.values());atomic(OUT/'TEMPORAL_VALIDATION_SELECTION.json',dict(status='FROZEN_BEFORE_TEMPORAL_VALIDATION',time=stamp(),arms=arms,rule='per-region late and persistent PDMS/safety plus matched original-time references',new_validation_results_used=False))
    probe('validation_temporal',arms)
    tasks=stage(ROOT/'runs'/RUN,'validation_temporal',read(ROOT/'repair_v1/validation.json'),arms,[0,1,2],chunk=8)
    print(json.dumps(dict(event='TEMPORAL_VALIDATION_APPENDED',tasks=tasks,arms=len(arms))),flush=True)

def main():
    setup('candidate_repair/temporal');compatibility()
    p=OUT/'TEMPORAL_PROTOCOL.json'
    if not p.exists():
        assert not (ROOT/'runs'/RUN/'stages/validation/PROTOCOL.json').exists()
        atomic(p,dict(status='ADAPTIVE_EXPLORATION_FROZEN_BEFORE_NEW_VALIDATION',time=stamp(),motivation='128-case fixed replay showed early latent deviations attenuating before final trajectory',
            sensitivity_sha256=sha(OUT/'SENSITIVITY.json'),candidates=4,arms=144,scope='same original route-one projectors; change timing and calibrated operator, not dimension search',
            fit_subset='exploration only',source_basis_preserved=True,relative_total_caps=[.01,.05],normalized_direction_alpha=1e6,
            alpha_meaning='large alpha forces fixed relative cap; effective strength is measured cap, never a million-fold actual hidden edit',
            final_choice_rule='same six route/global safety/PDMS roles; validation only; primary test family unchanged'))
    if not (ROOT/'runs'/RUN/'stages/temporal_screen/PROTOCOL.json').exists():prepare()
    if not (ROOT/'runs'/RUN/'stages/validation_temporal/PROTOCOL.json').exists():validate()
    atomic(OUT/'TEMPORAL_SETUP_COMPLETE.json',dict(status='PASS',time=stamp()))

if __name__=='__main__':main()
