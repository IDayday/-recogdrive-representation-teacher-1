"""Calibrate a full-token selector on excluded training sessions only."""
from r2_common import *


def choices(prediction,risk,threshold):
    import numpy as np
    gain=prediction[:,1:,0]-prediction[:,:1,0]
    damage=np.maximum(prediction[:,:1,1:3]-prediction[:,1:,1:3],0).sum(2)
    utility=np.clip(gain,-1.,1.)-risk*damage
    selected=utility.argmax(1)+1;selected[utility.max(1)<=threshold]=0
    return selected


def matrices(point,stage):
    import numpy as np
    output={k:[] for k in ['global_indices','seeds','scores','trajectory','predicted']};sources=[]
    for start in range(0,len(point['items']),8):
        path=ROOT/stage/'results'/(point['id']+'_%04d.npz'%start);meta=read(path.with_suffix('.json'));assert sha(path)==meta['sha256']
        with np.load(path) as z:
            for k in output:output[k].append(np.array(z[k]))
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=meta['sha256']))
    return {k:np.concatenate(v,0) for k,v in output.items()},sources


def run(task):
    import numpy as np
    from r2_token_critic import inner_session
    point=read(ROOT/task['point']);assert point['mode']=='calibration';held=point['heldout_fold'];data,lineage=matrices(point,task['stage'])
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);indices=data['global_indices'];s=data['scores'];prediction=data['predicted']
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    assert np.all(train[indices]) and all(inner_session(rows[i]['session']) for i in indices)
    classes=np.where(quality[indices]<.7,0,np.where(quality[indices]>.9,1,2));counts=np.bincount(classes,minlength=3);assert np.all(counts>0)
    population=[np.sum(train&(quality<.7)),np.sum(train&(quality>.9)),np.sum(train&(quality>=.7)&(quality<=.9))]
    weights=np.array([population[c]/counts[c] for c in classes]);weights/=weights.sum();candidates=[]
    for j,critic in enumerate(point['critics']):
        for risk in [0.,.1,.5,1.,2.,5.]:
            for threshold in [0.,.001,.005,.01,.02,.05,.1,2.]:
                choice=choices(prediction[:,j],risk,threshold);after=s[np.arange(len(s)),choice];base=s[:,0]
                rates=[float(np.sum(weights*((after[:,c]<1).astype(float)-(base[:,c]<1).astype(float)))) for c in [1,2]]
                rates.append(float(np.sum(weights*((after[:,0]==0).astype(float)-(base[:,0]==0).astype(float)))))
                gain=float(np.sum(weights*(after[:,0]-base[:,0])))
                candidates.append(dict(critic_index=j,risk_penalty=risk,threshold=threshold,pdms_gain=gain,collision_delta=rates[0],offroad_delta=rates[1],zero_delta=rates[2],safe=all(v<=1e-12 for v in rates),active_fraction=float(np.sum(weights*(choice>0)))))
    eligible=[p for p in candidates if p['safe']] if point['role']=='safety' else candidates;assert eligible
    chosen=max(eligible,key=lambda c:(c['pdms_gain'],-c['active_fraction']));critic=dict(point['critics'][chosen['critic_index']],risk_penalty=chosen['risk_penalty'],threshold=chosen['threshold'])
    path=ROOT/'token_policies'/point['id']/'POLICY.json';record=dict(status='CALIBRATED_NOT_HELDOUT_CONFIRMED',time=stamp(),system=point['system'],role=point['role'],heldout_fold=held,
        K=point['K'],wave=point['wave'],fit_seed=point['fit_seed'],kind='full_token_independent_selector',parts=point['parts'],critic=critic,
        candidates=candidates,selected_calibration=chosen,calibration_examples=len(s),calibration_cases=len(set(indices.tolist())),calibration_sessions=len({rows[i]['session'] for i in indices}),
        calibration_sources=lineage,source_point=task['point'],no_quality_GT_at_deployment=True,exact_Base_available=True,
        caveat='Training calibration reuses actual unchanged candidate outcomes; held-out whole-system evaluation remains necessary.',validation_accessed=False,test_accessed=False)
    atomic(path,record);return dict(path=str(path.relative_to(ROOT)),chosen=chosen,examples=len(s))
