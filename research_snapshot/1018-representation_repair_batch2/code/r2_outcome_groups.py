"""Natural expert initialization from real responses and bounded corrections.

Group membership is privileged training information. It is never a deployment
input, and every held-out-fold version refits all normalizers and clusters.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def correction_data():
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    failure=np.array([i for i,r in enumerate(rows) if r['subset']=='exploration' and q[i]<.7])
    mapping={int(i):j for j,i in enumerate(failure)}
    configurations=[(b,c) for b in ['interface_pre','interface_post'] for c in [.005,.02,.1]]
    response=np.full((len(failure),len(configurations),40),np.nan,dtype=np.float32)
    correction=np.full((len(failure),len(configurations),34),np.nan,dtype=np.float32)
    fields=['score','no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound',
            'ego_progress','comfort','driving_direction_compliance']
    projectors={}
    coverage=set()
    for path in sorted((ROOT/'analysis/case_corrections').glob('correction_interface_*.json')):
        d=read(path);i=mapping[d['global_index']];c=configurations.index((d['block'],d['cap']))
        assert (i,c) not in coverage;coverage.add((i,c))
        records=d['records'];base=records[0]['score'];chosen=records[d['selected_index']]['score']
        vector=[]
        vector.extend(chosen[f]-base[f] for f in fields)
        vector.extend(base[f] for f in fields)
        for j in [1,2]:
            matches={v['arm']:v['score'] for v in d['transfer'] if v['seed_index']==j}
            vector.extend(matches['selected_on_S0'][f]-matches['baseline'][f] for f in fields)
        vector.extend([records[d['selected_index']]['relative_edit'],d['selected_index']/max(len(records)-2,1),
                       records[0]['surrogate_loss'],records[d['selected_index']]['surrogate_loss']])
        # Entire response curve reveals conflicting perturbation directions even
        # when all cases have the same best score. Constant-zero cases remain.
        vector.extend(v['score']['score']-base['score'] for v in records[1:-1])
        assert len(vector)==38,len(vector)
        vector.extend([records[-1]['score']['score'],float(chosen['score']>.9)])
        response[i,c]=vector
        with np.load(ROOT/d['arrays']) as z:delta=np.array(z['actual_delta_mean'],dtype=np.float64)
        dim=len(delta)
        if dim not in projectors:
            rng=np.random.default_rng(20261018+dim);projectors[dim]=rng.normal(size=(dim,32))/np.sqrt(dim)
        norm=float(np.linalg.norm(delta))
        correction[i,c,:32]=(delta/max(norm,1e-10))@projectors[dim]
        correction[i,c,32:]=[norm,chosen['score']-base['score']]
    assert len(coverage)==len(failure)*6,(len(coverage),len(failure)*6)
    assert np.isfinite(response).all() and np.isfinite(correction).all()
    return rows,failure,response.reshape(len(failure),-1),correction.reshape(len(failure),-1)


def run(task):
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.utils.extmath import randomized_svd
    from scipy.special import softmax
    rows,all_failure,response,correction=correction_data()
    held=task['heldout_fold'];family=task['family']
    folds=np.array([int(digest(dict(session=rows[i]['session'],cv_root=20261016))[:8],16)%5 for i in all_failure])
    use=(folds!=held) if held>=0 else np.ones(len(folds),dtype=bool)
    indices=all_failure[use];raw=(response if family=='response' else np.concatenate([correction,response],1))[use]
    center=raw.mean(0);scale=np.maximum(raw.std(0),1e-5);standard=(raw-center)/scale
    # Limit rare binary threshold changes without deleting those cases.
    standard=np.clip(standard,-8,8)
    n=min(64,standard.shape[1],len(standard)-1)
    _,_,v=randomized_svd(standard,n_components=n,random_state=20261018)
    projected=standard@v.T;ps=np.maximum(projected.std(0),1e-5)
    features=projected/ps/np.sqrt(n)
    fold_name='all' if held<0 else f'fold{held}'
    with np.load(ROOT/'analysis/initial_groups'/fold_name/'representation_features.npz') as z:
        assert np.array_equal(indices,z['global_indices']);fallback=np.array(z['features'])
    # Preserve representation diversity among failures with no observed response.
    # This is an explicit initialization choice, not an oracle deployment gate.
    features=np.concatenate([features,.25*fallback],1)
    folder=ROOT/'analysis/outcome_groups'/fold_name;folder.mkdir(parents=True,exist_ok=True)
    feature_path=folder/(family+'_features.npz')
    with feature_path.open('wb') as f:np.savez(f,global_indices=indices,features=features.astype('float32'),
         response=response[use],correction=correction[use],center=center,scale=scale,basis=v.T,projection_scale=ps)
    records=[]
    for k in range(2,9):
        for replicate,value in enumerate(read(ROOT/'config/execution_v1.json')['fit_seeds']):
            model=KMeans(n_clusters=k,random_state=value,n_init=10).fit(features)
            distance=model.transform(features)**2
            temperature=max(float(np.median(np.min(distance,1)))*.25,1e-5)
            responsibility=softmax(-distance/temperature,axis=1)
            ident=f'{family}_K{k}_seed{replicate}';target=folder/(ident+'.npz')
            with target.open('wb') as f:np.savez(f,global_indices=indices,responsibility=responsibility.astype('float32'),
                    centers=model.cluster_centers_.astype('float32'),temperature=temperature)
            labels=model.labels_;count=np.bincount(labels,minlength=k)
            sessions=[len({rows[i]['session'] for i in indices[labels==e]}) for e in range(k)]
            ess=responsibility.sum(0)**2/np.maximum(np.square(responsibility).sum(0),1e-12)
            record=dict(id=ident,K=k,fit_seed=value,heldout_fold=held,path=str(target.relative_to(ROOT)),
                        sha256=sha(target),hard_counts=count.tolist(),sessions=sessions,effective_counts=ess.tolist(),
                        train_cases=len(indices),family=family,fit_only_training_fold=True,
                        privileged_membership=True,deployable_features=False,unresponsive_failures_retained=True)
            atomic(target.with_suffix('.json'),record);records.append(record)
    result=dict(status='PASS',time=stamp(),family=family,heldout_fold=held,train_failures=len(indices),
                initialization_systems=records,all_failures_included=True,
                feature_path=str(feature_path.relative_to(ROOT)),validation_fitted=False,test_accessed=False)
    atomic(folder/(family+'_COMPLETE.json'),result)
    return dict(path=str((folder/(family+'_COMPLETE.json')).relative_to(ROOT)),systems=len(records))
