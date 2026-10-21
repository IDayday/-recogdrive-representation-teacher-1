"""Fold-contained observable router features, with an explicit Base-first tier.

Neither quality labels, GT, nor metric-cache contents enter the feature values.
The known split restricts fitting; held-out observations are only transformed.
"""
from r2_common import *


def run(task):
    import numpy as np
    from sklearn.utils.extmath import randomized_svd
    from r2_expert_space import save_npz
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);held=task['heldout_fold']
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    fit_indices=np.array(sorted(np.flatnonzero(train),key=lambda i:digest(dict(token=rows[i]['token'],router_pca=20261018)))[:8192])
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    views=['vision_23__patch_mean','bridge_3__patch_mean','language_07__valid_mean',
           'language_15__valid_mean','interface_pre__valid_mean','interface_post__valid_mean']
    output=[];transforms={};lineage=[]
    for view in views:
        cell=cells[view];raw=np.load(cell['absolute_path'],mmap_mode='r')
        fit=np.asarray(raw[fit_indices],dtype=np.float64);mean=fit.mean(0);scale=fit.std(0)
        scale=np.maximum(scale,max(float(np.median(scale))*1e-3,1e-6))
        _,_,v=randomized_svd(np.clip((fit-mean)/scale,-20,20),n_components=32,random_state=20261018)
        std=np.maximum((np.clip((fit-mean)/scale,-20,20)@v.T).std(0),1e-5)
        z=np.empty((len(rows),32),dtype=np.float32)
        for start in range(0,len(rows),4096):
            a=np.asarray(raw[start:start+4096],dtype=np.float64)
            z[start:start+4096]=(np.clip((a-mean)/scale,-20,20)@v.T/std).astype('float32')
        assert np.isfinite(z).all();output.append(z)
        transforms[view+'_mean']=mean.astype('float32');transforms[view+'_scale']=scale.astype('float32')
        transforms[view+'_basis']=v.T.astype('float32');transforms[view+'_projection_scale']=std.astype('float32')
        lineage.append(dict(cell=view,source_sha256=cell['sha256'],rank=32))
    folder=ROOT/'router_features'/('all' if held<0 else f'fold{held}');target=folder/'features.npz'
    hashed=save_npz(target,observation=np.concatenate(output,1),fit_indices=fit_indices,**transforms)
    record=dict(status='PASS',time=stamp(),heldout_fold=held,path=str(target.relative_to(ROOT)),sha256=hashed,
          rows=len(rows),observation_dimension=192,fit_cases=len(fit_indices),source_views=lineage,
          fits_only_exploration_training_fold=True,quality_GT_or_metric_values_used_as_features=False,
          Base_first_tier='Append geometry from the current native trajectory, using that sample seed. Not stored S0 geometry for other seeds.',
          validation_fitted=False,test_accessed=False)
    atomic(folder/'COMPLETE.json',record);return dict(path=str((folder/'COMPLETE.json').relative_to(ROOT)),dimension=192)


def trajectory_features(trajectory):
    import numpy as np
    p=np.asarray(trajectory,dtype=np.float32);assert p.shape==(8,3)
    normalized=p.copy();normalized[:,:2]/=np.asarray([40.,10.],dtype=np.float32)
    # Sine/cosine avoid a spurious discontinuity at +/-pi.
    return np.concatenate([normalized[:,:2].reshape(-1),np.sin(p[:,2]),np.cos(p[:,2])]).astype('float32')


def from_engine(engine,arrays):
    """Same observable features at new scenes; no dataset index lookup required."""
    import torch
    views=['vision_23__patch_mean','bridge_3__patch_mean','language_07__valid_mean',
           'language_15__valid_mean','interface_pre__valid_mean','interface_post__valid_mean'];output=[]
    for view in views:
        block,group=view.split('__',1);h=engine.prefix[block];mask,valid=engine.mask(block,group);assert valid
        pooled=h.reshape(-1,h.shape[-1])[mask].float().mean(0)
        value=torch.clamp((pooled-arrays[view+'_mean'])/arrays[view+'_scale'],-20,20)
        output.append((value@arrays[view+'_basis'])/arrays[view+'_projection_scale'])
    return torch.cat(output)
