"""Observable, response-supervised hard-router warm starts with a zero option.

Inner session CV chooses model/risk/abstention settings. Only the outer held-out
policy rollout is whole-system CV; these training-library numbers are not that.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=6)
def context(held):
    import numpy as np
    folder=ROOT/'router_features'/('all' if held<0 else f'fold{held}');meta=read(folder/'COMPLETE.json')
    with np.load(ROOT/meta['path']) as z:return np.array(z['observation']),meta


def run(task):
    import numpy as np
    import pickle
    import sklearn
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import ExtraTreesRegressor
    from r2_router_features import trajectory_features
    selection=read(ROOT/task['selection']);held=selection['heldout_fold'];role=task['role'];tier=task['tier']
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    population=[np.sum(train&(quality<.7)),np.sum(train&(quality>.9)),np.sum(train&(quality>=.7)&(quality<=.9))]
    arms=selection['arms'];by_id={a['id']:a for a in arms}
    ordered=sorted(selection['policies'][role].items(),key=lambda p:int(p[0]));parts=[by_id[ident] for _,ident in ordered]
    ids=[p['id'] for p in parts];obs,feature_meta=context(held)
    features=[];labels=[];scores=[];weights=[];sessions=[];indices=[];noise_indices=[]
    for response_path in task['responses']:
        response=read(ROOT/response_path);point=read(ROOT/response['point'])
        assert point['heldout_fold']==held and point['training_only']
        with np.load(ROOT/response['matrix']) as z:
            ii=np.array(z['global_indices']);aa=list(z['arm_ids']);ss=np.array(z['seeds']);s=np.array(z['scores'])
            trajectories=np.array(z['trajectory']);states=np.array(z['base_action_states'])
        assert np.all(train[ii]);selected=[0]+[aa.index(ident) for ident in ids]
        classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
        for j,index in enumerate(ii):
            for n,noise in enumerate(ss):
                x=[obs[index]]
                if tier in ['trajectory','denoising']:x.append(trajectory_features(trajectories[j,0,n]))
                if tier=='denoising':x.append(states[j,n].reshape(-1))
                features.append(np.concatenate(x));a=s[j,selected,n];base=a[0];after=a[1:]
                y=np.column_stack([after[:,0]-base[0],(after[:,1]<1).astype(float)-float(base[1]<1),
                    (after[:,2]<1).astype(float)-float(base[2]<1),(after[:,0]==0).astype(float)-float(base[0]==0),
                    (after[:,0]<base[0]-.05).astype(float)])
                labels.append(y);scores.append(a);weights.append(float(population[classes[j]]/counts[classes[j]]))
                sessions.append(rows[index]['session']);indices.append(int(index));noise_indices.append(int(noise))
    x=np.asarray(features,dtype=np.float64);y=np.asarray(labels,dtype=np.float64);actual=np.asarray(scores);w=np.asarray(weights)
    assert np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(w).all()
    inner=np.array([int(digest(dict(session=s,router_inner=20261018))[:8],16)%3 for s in sessions]);assert len(set(inner))==3
    configurations=[dict(kind='ridge',alpha=a) for a in [.1,1.,10.,100.]]
    configurations += [dict(kind='trees',depth=d,leaf=l) for d in [8,16] for l in [8,32]]
    seed_root=int(digest(dict(system=selection['system'],held=held,role=role,tier=tier,router_fit=20261018))[:8],16)
    def fit(spec,use,salt):
        xx=x[use];ww=w[use];mean=np.average(xx,axis=0,weights=ww);scale=np.sqrt(np.average((xx-mean)**2,axis=0,weights=ww));scale=np.maximum(scale,1e-5)
        model=Ridge(alpha=spec['alpha']) if spec['kind']=='ridge' else ExtraTreesRegressor(n_estimators=128,max_depth=spec['depth'],min_samples_leaf=spec['leaf'],max_features=.75,n_jobs=1,random_state=(seed_root+salt)%2**32)
        model.fit((xx-mean)/scale,y[use].reshape(len(xx),-1),sample_weight=ww/ww.mean())
        return dict(model=model,mean=mean,scale=scale)
    def predict(model,use):return model['model'].predict((x[use]-model['mean'])/model['scale']).reshape(-1,len(parts),5)
    def assess(pred,risk,tau):
        penalty=np.maximum(pred[:,:,1:4],0).sum(2)+.1*np.maximum(pred[:,:,4],0)
        utility=np.clip(pred[:,:,0],-1.,1.)-risk*penalty;choice=utility.argmax(1)+1;choice[np.max(utility,1)<=tau]=0
        result=actual[np.arange(len(actual)),choice];base=actual[:,0];total=w.sum()
        gain=float(np.sum(w*(result[:,0]-base[:,0]))/total)
        deltas=[float(np.sum(w*((result[:,c]<1).astype(float)-(base[:,c]<1).astype(float)))/total) for c in [1,2]]
        deltas.append(float(np.sum(w*((result[:,0]==0).astype(float)-(base[:,0]==0).astype(float)))/total))
        return dict(pdms_gain=gain,weighted_collision_rate_delta=deltas[0],weighted_offroad_rate_delta=deltas[1],
                    weighted_zero_rate_delta=deltas[2],active_fraction=float(np.sum(w*(choice>0))/total),
                    safe_estimate=all(v<=1e-12 for v in deltas))
    candidates=[];oofs=[]
    for number,spec in enumerate(configurations):
        pred=np.full_like(y,np.nan)
        for fold in range(3):
            model=fit(spec,inner!=fold,number*10+fold);pred[inner==fold]=predict(model,inner==fold)
        assert np.isfinite(pred).all();oofs.append(pred)
        for risk in [0.,.1,.5,1.,2.,5.]:
            for tau in [0.,.001,.005,.01,.02,.05,.1,2.]:
                metrics=assess(pred,risk,tau);candidates.append(dict(model_index=number,model_spec=spec,risk_penalty=risk,threshold=tau,metrics=metrics))
    eligible=[c for c in candidates if c['metrics']['safe_estimate']] if role=='safety' else candidates
    assert eligible # threshold=2 is the exact identity fallback.
    chosen=max(eligible,key=lambda c:(c['metrics']['pdms_gain'],-c['metrics']['active_fraction']))
    final=fit(chosen['model_spec'],np.ones(len(x),dtype=bool),999)
    folder=ROOT/'routers'/task['id'];folder.mkdir(parents=True,exist_ok=False);path=folder/'model.pkl'
    with path.open('wb') as stream:pickle.dump(final,stream,protocol=4)
    metadata=dict(status='WARM_HARD_ROUTER_FITTED',time=stamp(),task=task,system=selection['system'],heldout_fold=held,
          nominal_K=selection['K'],active_K=len(parts),role=role,tier=tier,kind='hard_fixed_configuration_warm',
          parts=parts,model_path=str(path.relative_to(ROOT)),model_sha256=sha(path),feature_meta=feature_meta,
          risk_penalty=chosen['risk_penalty'],threshold=chosen['threshold'],inner_selection=chosen,
          candidates=candidates,rows=len(x),unique_cases=len(set(indices)),fit_seed=seed_root,
          sklearn_version=sklearn.__version__,numpy_version=np.__version__,training_noise_indices=sorted(set(noise_indices)),
          exact_identity_available=True,predicted_gain_clip=[-1.,1.],PDMS_GT_not_input_features=True,outer_whole_system_cv_pending=True,
          caveat='Inner routing CV is conditional on outer-training experts. This is not held-out whole-system performance.',
          validation_fitted=False,test_accessed=False)
    atomic(folder/'POLICY.json',metadata)
    return dict(path=str((folder/'POLICY.json').relative_to(ROOT)),chosen=chosen,rows=len(x),nominal_K=selection['K'],active_K=len(parts))
