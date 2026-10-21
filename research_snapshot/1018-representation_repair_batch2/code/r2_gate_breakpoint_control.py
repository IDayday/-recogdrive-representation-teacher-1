"""Calibration-resolution control with frozen experts/readout checkpoint.

All empirical threshold decision sets are scanned for each declared risk value.
Rules are saved before held outcomes are read. Complete candidate trajectories
and their original real scores are reused without new inference or scoring.
"""
from r2_common import *


def utility(prediction,risk):
    import numpy as np
    gain=prediction[:,1:,0]-prediction[:,:1,0]
    damage=np.maximum(prediction[:,:1,1:3]-prediction[:,1:,1:3],0).sum(2)
    return np.clip(gain,-1.,1.)-risk*damage


def assess(prediction,scores,w,risk,threshold):
    import numpy as np
    from r2_token_policy_select import choices
    chosen=choices(prediction,risk,threshold);after=scores[np.arange(len(chosen)),chosen];base=scores[:,0]
    rates=[float(w@((after[:,c]<1).astype(float)-(base[:,c]<1).astype(float))) for c in [1,2]]
    rates.append(float(w@((after[:,0]==0).astype(float)-(base[:,0]==0).astype(float))))
    return dict(pdms_gain=float(w@(after[:,0]-base[:,0])),collision_delta=rates[0],offroad_delta=rates[1],zero_delta=rates[2],safe=all(v<=1e-12 for v in rates),active_fraction=float(w@(chosen>0)))


def curves(prediction,scores,w,risks,old_thresholds):
    import numpy as np
    output=[];base=scores[:,0];proofs=0
    for risk in risks:
        u=utility(prediction,risk);best=u.argmax(1)+1;maximum=u.max(1);after=scores[np.arange(len(best)),best]
        raw=np.column_stack([after[:,0]-base[:,0],(after[:,1]<1).astype(float)-(base[:,1]<1),
            (after[:,2]<1).astype(float)-(base[:,2]<1),(after[:,0]==0).astype(float)-(base[:,0]==0),np.ones(len(w))])
        order=np.argsort(maximum,kind='stable');prefix=np.vstack([np.zeros((1,5)),np.cumsum(raw[order]*w[order,None],axis=0)]);total=prefix[-1]
        # Cast threshold representatives to the utility dtype, matching the
        # original NumPy scalar comparisons. Observed utility cutoffs preserve
        # all distinct calibration decisions, including tied utility values.
        thresholds=np.unique(np.concatenate([np.asarray(old_thresholds,dtype=maximum.dtype),maximum[maximum>=0]]))
        boundaries=np.searchsorted(maximum[order],thresholds,side='right');values=total[None]-prefix[boundaries]
        for threshold,value in zip(thresholds,values):
            output.append(dict(risk_penalty=float(risk),threshold=float(threshold),pdms_gain=float(value[0]),collision_delta=float(value[1]),offroad_delta=float(value[2]),zero_delta=float(value[3]),safe=bool(np.all(value[1:4]<=1e-12)),active_fraction=float(value[4])))
        checks=sorted(set([0,len(thresholds)-1,*np.linspace(0,len(thresholds)-1,min(10,len(thresholds)),dtype=int).tolist()]))
        for index in checks:
            direct=assess(prediction,scores,w,risk,float(thresholds[index]));value=values[index]
            assert np.allclose([direct[k] for k in ['pdms_gain','collision_delta','offroad_delta','zero_delta','active_fraction']],value,rtol=0,atol=1e-10)
            proofs+=1
    return output,proofs


def stage_of_source(lineage):
    p=Path(lineage[0]['path']);assert p.parent.name=='results';return str(p.parent.parent)


def run(task):
    import numpy as np
    from r2_token_policy_select import matrices,choices
    from r2_token_critic import inner_session
    from r2_expert_space import save_npz
    protocol=read(ROOT/task['protocol']);assert sha(ROOT/task['protocol'])==task['protocol_sha256']
    original=read(ROOT/task['policy']);assert sha(ROOT/task['policy'])==task['policy_sha256']
    held=original['heldout_fold'];assert held>=0;point=read(ROOT/original['source_point']);cal,cal_sources=retry(lambda:matrices(point,stage_of_source(original['calibration_sources'])))
    j=original['selected_calibration']['critic_index'];assert point['critics'][j]['checkpoint']==original['critic']['checkpoint'];prediction=cal['predicted'][:,j];scores=cal['scores']
    assert prediction.shape[1]==len(original['parts'])+1==scores.shape[1]
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);ii=cal['global_indices']
    allowed=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held for r in rows]);assert np.all(allowed[ii]) and all(inner_session(rows[int(i)]['session']) for i in ii)
    cls=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(cls,minlength=3);assert np.all(counts>0)
    population=np.array([np.sum(allowed&(quality<.7)),np.sum(allowed&(quality>.9)),np.sum(allowed&(quality>=.7)&(quality<=.9))]);w=population[cls]/counts[cls];w/=w.sum()
    reference=assess(prediction,scores,w,original['critic']['risk_penalty'],original['critic']['threshold'])
    for field in ['pdms_gain','collision_delta','offroad_delta','zero_delta','active_fraction']:assert abs(reference[field]-original['selected_calibration'][field])<1e-10
    assert np.all(choices(prediction,0.,2.)==0)
    grid,checks=curves(prediction,scores,w,protocol['dense_risks'],protocol['old_thresholds'])
    prefix='gate_breakpoint_engineering' if task.get('engineering') else 'gate_breakpoints';folder=ROOT/prefix/task['id'];folder.mkdir(parents=True,exist_ok=False)
    curvepath=folder/'calibration_curves.npz';columns=['risk_penalty','threshold','pdms_gain','collision_delta','offroad_delta','zero_delta','active_fraction'];curvehash=save_npz(curvepath,values=np.array([[r[k] for k in columns] for r in grid]),columns=np.asarray(columns))
    outputs={}
    for variant in protocol['variants']:
        risks=protocol['old_risks'] if variant=='exact_threshold' else protocol['dense_risks']
        # Original chosen rule comes first so equal calibration utility and
        # activity preserve it, including its globally exact Base fallback.
        original_entry=dict(reference,risk_penalty=original['critic']['risk_penalty'],threshold=original['critic']['threshold'])
        values=[original_entry]+[r for r in grid if r['risk_penalty'] in risks];eligible=[r for r in values if r['safe']] if original['role']=='safety' else values;assert eligible
        gain=max(r['pdms_gain'] for r in eligible);near=[r for r in eligible if r['pdms_gain']>=gain-protocol['numeric_gain_tie_tolerance']]
        minimum_activity=min(r['active_fraction'] for r in near)
        selected=next(r for r in near if r['active_fraction']<=minimum_activity+protocol['numeric_gain_tie_tolerance'])
        direct=assess(prediction,scores,w,selected['risk_penalty'],selected['threshold'])
        assert direct['pdms_gain']+1e-10>=reference['pdms_gain']
        if original['role']=='safety':assert direct['safe']
        policy=dict(original,status='DENSE_CALIBRATED_BEFORE_HELD_READ',time=stamp(),critic=dict(original['critic'],risk_penalty=selected['risk_penalty'],threshold=selected['threshold']),
            selected_calibration=dict(direct,critic_index=j,risk_penalty=selected['risk_penalty'],threshold=selected['threshold']),calibration_control=variant,
            original_policy=task['policy'],original_policy_sha256=task['policy_sha256'],original_selected_calibration=original['selected_calibration'],
            fixed_original_checkpoint=True,calibration_search_curve=str(curvepath.relative_to(ROOT)),calibration_search_curve_sha256=curvehash,
            search_protocol=task['protocol'],search_protocol_sha256=task['protocol_sha256'],candidates=None)
        path=folder/variant/'POLICY.json';atomic(path,policy);outputs[variant]=dict(policy=policy,path=str(path.relative_to(ROOT)),sha256=sha(path),calibration_gain_points=direct['pdms_gain']*100)
    # Only after both rules are frozen do we open any held prediction/outcome.
    assert sha(ROOT/task['assessment'])==task['assessment_sha256'];assessment=read(ROOT/task['assessment'])
    first=Path(assessment['sources'][0]['path']);heldstage=first.parent.parent;heldid=first.stem.rsplit('_',1)[0];heldpointpath=ROOT/heldstage/'points'/(heldid+'.json');heldpoint=read(heldpointpath)
    assert heldpoint['policy']==task['policy'] and heldpoint['critics'][0]['checkpoint']==original['critic']['checkpoint'];data,held_sources=retry(lambda:matrices(heldpoint,str(heldstage)));assert data['predicted'].shape[1]==1
    hp=data['predicted'][:,0];indices=data['global_indices'];noises=data['seeds'];assert all(rows[int(i)]['subset']=='exploration' and int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5==held for i in indices)
    oldchoices=choices(hp,original['critic']['risk_penalty'],original['critic']['threshold']);assert sha(ROOT/assessment['matrix'])==assessment['matrix_sha256']
    with np.load(ROOT/assessment['matrix']) as z:
        assert np.array_equal(z['global_indices'],indices) and np.array_equal(z['seeds'],noises) and np.array_equal(z['choice'],oldchoices)
        assert np.array_equal(z['selected_scores'],data['scores'][np.arange(len(indices)),oldchoices]) and np.array_equal(z['trajectory'],data['trajectory'][np.arange(len(indices)),oldchoices])
    unique=sorted(set(indices.tolist()));lookup={i:j for j,i in enumerate(unique)};seen=set();out=[]
    assert sorted(set(noises.tolist()))==[0,1,2] and len(indices)==3*len(unique)
    for variant,record in outputs.items():
        policy=record['policy'];choice=choices(hp,policy['critic']['risk_penalty'],policy['critic']['threshold']);after=data['scores'][np.arange(len(choice)),choice];trajectory=data['trajectory'][np.arange(len(choice)),choice]
        score=np.full((len(unique),2,3,7),np.nan);paths=np.full((len(unique),2,3,8,3),np.nan,dtype=np.float32);seen=set()
        for row,(i,n) in enumerate(zip(indices,noises)):
            key=lookup[int(i)],int(n);assert key not in seen;seen.add(key);score[key[0],0,key[1]]=data['scores'][row,0];score[key[0],1,key[1]]=after[row];paths[key[0],0,key[1]]=data['trajectory'][row,0];paths[key[0],1,key[1]]=trajectory[row]
        assert np.isfinite(score).all() and np.isfinite(paths).all()
        ident=task['id']+'_'+variant;destination=ROOT/('analysis/gate_breakpoint_engineering/projections' if task.get('engineering') else 'analysis/responses/token_full_cv_projection_v1');matrix=destination/(ident+'.npz');hashed=save_npz(matrix,global_indices=np.asarray(unique),seeds=np.array([0,1,2]),arm_ids=np.asarray(['baseline',original['role']]),scores=score,trajectory=paths)
        pp=ROOT/'analysis/gate_breakpoint_points'/(ident+'.json');atomic(pp,dict(id=ident,system=original['system'],heldout_fold=held,mode='heldout',kind='wave1',panel=unique,seeds=[0,1,2],policy=record['path'],policy_sha256=record['sha256'],fixed_checkpoint=True,calibration_resolution_only=True))
        meta=destination/(ident+'.json');atomic(meta,dict(status='COMPLETE',time=stamp(),source_mode='heldout',task=dict(stage='runs/token_breakpoint_'+task['view']+'_'+variant+'_cv_v1'),point=str(pp.relative_to(ROOT)),matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,
            policy=record['path'],policy_sha256=record['sha256'],actual_trajectories_and_scores_reused=True,source_assessment=task['assessment'],source_assessment_sha256=task['assessment_sha256'],source_predictions=held_sources,policy_frozen_before_held_read=True,no_new_inference_or_scoring=True,validation_accessed=False,test_accessed=False));out.append(dict(variant=variant,path=str(meta.relative_to(ROOT)),policy=record['path'],calibration_gain_points=record['calibration_gain_points']))
    summary=folder/'SUMMARY.json';atomic(summary,dict(status='PASS_EXISTING_DATA_DENSE_GATE_CONTROL',time=stamp(),task=task,outputs=out,curve_direct_original_rule_checks=checks,old_calibration_metrics_reproduced_to_1e10=True,old_held_choices_scores_andtrajectories_bitwise_exact=True,fixed_experts_critic_andcheckpoint=True,all_threshold_decision_sets_in_calibration_scanned=True,calibration_cases=len(set(ii.tolist())),held_cases=len(unique),new_model_training=0,new_rollouts=0,new_scoring=0,no_heldout_selection=True))
    return dict(path=str(summary.relative_to(ROOT)),outputs=out)
