"""Observable-only router inference with an explicit exact Base option."""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=64)
def model(path,expected):
    import pickle
    assert sha(ROOT/path)==expected
    with (ROOT/path).open('rb') as stream:return pickle.load(stream)


@lru_cache(maxsize=6)
def transforms(path,expected):
    import numpy as np
    import torch
    assert sha(ROOT/path)==expected
    with np.load(ROOT/path) as z:
        return {k:torch.tensor(np.array(z[k]),device='cuda',dtype=torch.float32) for k in z.files
                if k.endswith(('_mean','_scale','_basis','_projection_scale'))}


def feature(engine,base,states,policy):
    import numpy as np
    from r2_router_features import from_engine,trajectory_features
    meta=policy['feature_meta'];key=(id(engine.inputs),meta['path'])
    if getattr(engine,'router_feature_key',None)!=key:
        engine.router_observation=from_engine(engine,transforms(meta['path'],meta['sha256'])).detach().cpu().numpy()
        engine.router_feature_key=key
        engine.router_feature_inputs=engine.inputs
    pieces=[engine.router_observation]
    if policy['tier'] in ['trajectory','denoising']:pieces.append(trajectory_features(base))
    if policy['tier']=='denoising':pieces.append(np.asarray(states,dtype=np.float32).reshape(-1))
    return np.concatenate(pieces).astype('float64')


def decide(policy,x):
    import numpy as np
    assert policy['PDMS_GT_not_input_features'] and policy['exact_identity_available']
    fitted=model(policy['model_path'],policy['model_sha256'])
    pred=fitted['model'].predict(((x-fitted['mean'])/fitted['scale'])[None]).reshape(len(policy['parts']),5)
    assert np.isfinite(pred).all()
    penalty=np.maximum(pred[:,1:4],0).sum(1)+.1*np.maximum(pred[:,4],0)
    utility=np.clip(pred[:,0],-1.,1.)-policy['risk_penalty']*penalty
    index=int(utility.argmax());choice=index+1 if utility[index]>policy['threshold'] else 0
    return choice,dict(max_predicted_utility=float(utility[index]),selected_predicted_gain=float(pred[index,0]),
                       threshold=policy['threshold'],predicted_damage=float(pred[index,4]))
