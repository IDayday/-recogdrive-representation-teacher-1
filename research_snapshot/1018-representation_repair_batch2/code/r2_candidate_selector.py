"""Outcome-supervised selection among independently generated whole trajectories.

The shared critic sees observable context and candidate geometry, never GT,
metric cache contents or a quality label. Base has exact relative utility zero.
"""
from r2_common import *


def inputs(observation,baseline,candidates,states,slots,tier):
    import numpy as np
    from r2_router_features import trajectory_features
    base=trajectory_features(baseline);features=[]
    for candidate,slot in zip(candidates,slots):
        c=trajectory_features(candidate);onehot=np.zeros(8,dtype=np.float32);onehot[slot]=1
        pieces=[observation,base,c,c-base,onehot]
        if tier=='denoising':pieces.append(np.asarray(states).reshape(-1))
        features.append(np.concatenate(pieces))
    return np.asarray(features,dtype=np.float64)


def run(task):
    import numpy as np
    import pickle
    import sklearn
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import ExtraTreesRegressor
    from r2_router_fit import context
    selection=read(ROOT/task['selection']);held=selection['heldout_fold'];role=task['role'];tier=task['tier']
    by_id={p['id']:p for p in selection['arms']};parts=[by_id[v] for _,v in sorted(selection['policies'][role].items(),key=lambda z:int(z[0]))]
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    population=np.array([np.sum(train&(quality<.7)),np.sum(train&(quality>.9)),np.sum(train&(quality>=.7)&(quality<=.9))])
    observation,meta=context(held);xx=[];yy=[];actual=[];weight=[];sessions=[];cases=[]
    for response_path in task['responses']:
        response=read(ROOT/response_path);point=read(ROOT/response['point']);assert point['heldout_fold']==held and point['training_only']
        with np.load(ROOT/response['matrix']) as z:
            ii=np.array(z['global_indices']);ids=list(z['arm_ids']);scores=np.array(z['scores']);trajectory=np.array(z['trajectory']);states=np.array(z['base_action_states'])
        assert np.all(train[ii]);pick=[0]+[ids.index(p['id']) for p in parts];classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
        for j,index in enumerate(ii):
            for n in range(scores.shape[2]):
                chosen=scores[j,pick,n];base=chosen[0];after=chosen[1:]
                xx.append(inputs(observation[index],trajectory[j,0,n],trajectory[j,pick[1:],n],states[j,n],[p['slot'] for p in parts],tier))
                yy.append(np.column_stack([after[:,0]-base[0],(after[:,1]<1).astype(float)-float(base[1]<1),
                    (after[:,2]<1).astype(float)-float(base[2]<1),(after[:,0]==0).astype(float)-float(base[0]==0),(after[:,0]<base[0]-.05).astype(float)]))
                actual.append(chosen);weight.append(population[classes[j]]/counts[classes[j]]);sessions.append(rows[index]['session']);cases.append(int(index))
    x=np.asarray(xx);y=np.asarray(yy);s=np.asarray(actual);w=np.asarray(weight);count=len(parts)
    assert np.isfinite(x).all() and np.isfinite(y).all()
    inner=np.array([int(digest(dict(session=t,selector_inner=20261018))[:8],16)%3 for t in sessions])
    configurations=[dict(kind='ridge',alpha=a) for a in [.1,1.,10.,100.]]+[dict(kind='trees',depth=d,leaf=l) for d in [8,16] for l in [8,32]]
    fit_seed=int(digest(dict(system=selection['system'],held=held,tier=tier,role=role,selector_fit=20261018))[:8],16)
    def fit(spec,use,salt):
        a=x[use].reshape(-1,x.shape[-1]);b=y[use].reshape(-1,5);ww=np.repeat(w[use],count);ww/=ww.mean()
        mean=np.average(a,axis=0,weights=ww);scale=np.sqrt(np.average((a-mean)**2,axis=0,weights=ww));scale=np.maximum(scale,1e-5)
        model=Ridge(alpha=spec['alpha']) if spec['kind']=='ridge' else ExtraTreesRegressor(n_estimators=128,max_depth=spec['depth'],min_samples_leaf=spec['leaf'],max_features=.75,n_jobs=1,random_state=(fit_seed+salt)%2**32)
        model.fit((a-mean)/scale,b,sample_weight=ww);return dict(model=model,mean=mean,scale=scale)
    def predict(model,use):
        a=x[use];return model['model'].predict((a.reshape(-1,a.shape[-1])-model['mean'])/model['scale']).reshape(-1,count,5)
    candidates=[]
    for number,spec in enumerate(configurations):
        pred=np.full_like(y,np.nan)
        for fold in range(3):
            m=fit(spec,inner!=fold,number*10+fold);pred[inner==fold]=predict(m,inner==fold)
        assert np.isfinite(pred).all()
        for risk in [0.,.1,.5,1.,2.,5.]:
            utility=np.clip(pred[:,:,0],-1,1)-risk*(np.maximum(pred[:,:,1:4],0).sum(2)+.1*np.maximum(pred[:,:,4],0))
            for threshold in [0.,.001,.005,.01,.02,.05,.1,2.]:
                choice=utility.argmax(1)+1;choice[utility.max(1)<=threshold]=0;selected=s[np.arange(len(s)),choice];base=s[:,0]
                rates=[float(np.sum(w*((selected[:,c]<1).astype(float)-(base[:,c]<1).astype(float)))/w.sum()) for c in [1,2]]
                rates.append(float(np.sum(w*((selected[:,0]==0).astype(float)-(base[:,0]==0).astype(float)))/w.sum()))
                metrics=dict(pdms_gain=float(np.sum(w*(selected[:,0]-base[:,0]))/w.sum()),weighted_collision_rate_delta=rates[0],weighted_offroad_rate_delta=rates[1],weighted_zero_rate_delta=rates[2],safe_estimate=all(v<=1e-12 for v in rates),active_fraction=float(np.sum(w*(choice>0))/w.sum()))
                candidates.append(dict(model_index=number,model_spec=spec,risk_penalty=risk,threshold=threshold,metrics=metrics))
    eligible=[c for c in candidates if c['metrics']['safe_estimate']] if role=='safety' else candidates
    assert eligible;chosen=max(eligible,key=lambda c:(c['metrics']['pdms_gain'],-c['metrics']['active_fraction']))
    final=fit(chosen['model_spec'],np.ones(len(x),dtype=bool),999);folder=ROOT/'candidate_selectors'/task['id'];folder.mkdir(parents=True,exist_ok=False);path=folder/'model.pkl'
    with path.open('wb') as stream:pickle.dump(final,stream,protocol=4)
    record=dict(status='SELECTOR_FITTED_NOT_HELDOUT_VALIDATED',time=stamp(),task=task,kind='independent_candidate_selector',
        system=selection['system'],heldout_fold=held,nominal_K=selection['K'],active_K=len(parts),parts=parts,role=role,tier=tier,
        model_path=str(path.relative_to(ROOT)),model_sha256=sha(path),feature_meta=meta,risk_penalty=chosen['risk_penalty'],threshold=chosen['threshold'],
        candidates=candidates,inner_selection=chosen,rows=len(x),unique_cases=len(set(cases)),fit_seed=fit_seed,
        exact_identity_available=True,GT_PDMS_not_input_features=True,independent_complete_trajectories=True,
        no_trajectory_coordinate_averaging=True,training_diagnostics_not_whole_system_cv=True,
        sklearn_version=sklearn.__version__,numpy_version=np.__version__,validation_fitted=False,test_accessed=False)
    atomic(folder/'POLICY.json',record);return dict(path=str((folder/'POLICY.json').relative_to(ROOT)),rows=len(x),chosen=chosen)


def decide(policy,x):
    import numpy as np
    from r2_router_runtime import model
    fitted=model(policy['model_path'],policy['model_sha256']);pred=fitted['model'].predict((x-fitted['mean'])/fitted['scale'])
    penalty=np.maximum(pred[:,1:4],0).sum(1)+.1*np.maximum(pred[:,4],0)
    utility=np.clip(pred[:,0],-1,1)-policy['risk_penalty']*penalty
    choice=int(utility.argmax())+1 if utility.max()>policy['threshold'] else 0
    return choice,dict(predicted_utilities=utility.tolist(),threshold=policy['threshold'])
