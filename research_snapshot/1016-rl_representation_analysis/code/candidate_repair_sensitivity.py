"""Read-only mechanistic replay: distinguish weak action sensitivity from later denoising attenuation."""
from common import *
import numpy as np
from candidate_repair_fit import OUT
from candidate_repair_queue import Dispatch

def main():
    setup('candidate_repair/sensitivity');compatibility()
    import torch
    from worker import load_model,load_features
    from repair_engine import trace,geometries
    panel=read(OUT/'coarse_panel.json');arms=read(OUT/'coarse_arms.json');selected=[]
    for candidate in read(OUT/'CANDIDATES.json')['candidates']:
        a=next(a for a in arms if a['candidate']==candidate['id'] and a['space']=='candidate' and a['method']=='mean' and a['calibration']=='n' and a['gate']=='none' and a['alpha']==1. and a['cap']==.05)
        selected.append(a)
        if candidate['id'] in ['r1_pooled_centered_unequal_region0','r2_pooled_centered_unequal_region9']:
            for rep in [0,1,2]:selected.append(dict(a,id=a['id']+'_sens_haar'+str(rep),control_kind='haar_rotation',alternative_basis=candidate['id']+'__haar'+str(rep),parent=a['id']))
    rows=[]
    for label,n in [('failure',64),('high_quality',48),('intermediate',16)]:
        group=sorted([r for r in panel if r['quality']==label],key=lambda r:digest(dict(token=r['token'],sensitivity=20261016)));rows+=group[:n]
    cfg=read(ROOT/'configs/baseline.json');agent,runtime=load_model(cfg);editor=Dispatch(agent.action_head);head=agent.action_head
    versions={k:p._version for k,p in agent.named_parameters()};old=head.p_mean_variance;current={};frames=[]
    def decoder(module,inputs,h):
        if current:current['decoder']=h.detach().cpu().numpy().copy()
    handle=head.action_decoder.register_forward_hook(decoder)
    def observed(x,t,index,*args,**kwargs):
        current.clear();current['active']=True
        mean,lv,x0=old(x,t,index,*args,**kwargs)
        frames.append(dict(step=int(index[0]),latent=x.detach().cpu().numpy().copy(),mean=mean.detach().cpu().numpy().copy(),x0=x0.detach().cpu().numpy().copy(),decoder=current['decoder']))
        return mean,lv,x0
    def capture(chain,a):
        nonlocal frames
        frames=[];head.p_mean_variance=observed
        try:pred,metrics=editor.predict(chain,a)
        finally:head.p_mean_variance=old;current.clear()
        return pred,metrics,frames
    records=[];positions={r['token']:i for i,r in enumerate(panel)}
    try:
        for row in rows:
            features,_,_=load_features(row,cfg)
            with torch.no_grad():
                chain=trace(agent,features,seed(row['token']));baselines={}
                offset=(positions[row['token']]//2)*2
                stored=read(ROOT/'runs/candidate_repair_20261016_v1/results'/f'coarse_s0_{offset:06d}.json')
                expected={r['arm']:r for r in stored['records'] if r['token']==row['token']}
                for a in selected:
                    if a['step'] not in baselines:
                        pred,_,f=capture(chain,dict(a,alpha=0.));assert np.array_equal(pred,chain['trajectory']);baselines[a['step']]=f
                    pred,metrics,f=capture(chain,a);base=baselines[a['step']];assert len(f)==len(base)==5-a['step']
                    if 'parent' not in a:assert np.array_equal(pred,expected[a['id']]['trajectory'])
                    deltas=[]
                    for actual,before in zip(f,base):
                        assert actual['step']==before['step']
                        deltas.append(dict(step=actual['step'],**{k+'_l2':float(np.linalg.norm(actual[k]-before[k])) for k in ['latent','mean','x0','decoder']}))
                    records.append(dict(token=row['token'],quality=row['quality'],candidate=a['candidate'],arm=a['id'],control=a.get('control_kind'),
                        step=a['step'],metrics=metrics,geometry=geometries(pred,chain['trajectory']),deltas=deltas))
            print(json.dumps(dict(event='SENSITIVITY_CASE',done=len(records)//len(selected),total=len(rows))),flush=True)
    finally:head.p_mean_variance=old;handle.remove();editor.close()
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    result=[]
    for a in selected:
        group=[r for r in records if r['arm']==a['id']]
        summaries=[]
        for j in range(5-a['step']):
            summaries.append(dict(step=a['step']+j,**{k:np.quantile([r['deltas'][j][k] for r in group],[.1,.5,.9]).tolist() for k in ['latent_l2','mean_l2','x0_l2','decoder_l2']}))
        result.append(dict(arm=a,cases=len(group),relative_edit_median=float(np.median([r['metrics']['relative_edit_max'] for r in group])),
            displacement_median_m=float(np.median([r['geometry']['trajectory_displacement_max_m'] for r in group])),steps=summaries))
    atomic(OUT/'SENSITIVITY.json',dict(status='PASS',time=stamp(),cases=len(rows),arms=len(selected),summaries=result,records=records,runtime=runtime,
        fitted_population_only=True,used_for_selection=False,coarse_trajectories_exact=True,base_unchanged=True,scope='Fixed alpha1/cap.05 natural mean direction; representative exploration cases, not a global causal diagnosis'))

if __name__=='__main__':main()
