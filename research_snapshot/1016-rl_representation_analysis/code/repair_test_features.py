"""Strict, read-only adapter for the verified 1010 navtest cache schema.
Training anchors retain their original loader; no metadata rewriting or extraction.
"""
from common import *
import gzip
import pickle

def load_features(row,config):
    if row.get('cohort')!='navtest':
        from worker import load_features as original
        return original(row,config)
    import torch
    folder=Path(row['feature_dir']);identity=read(folder/'complete.json')
    assert identity['token']==row['token'] and identity['vlm_sha256']==config['vlm_sha256']
    assert identity['execution_protocol_sha256']==config['test_cache_execution_protocol_sha256']
    assert identity['vlm_dtype']=='torch.bfloat16' and sha(folder/'complete.json')==row['cache_identity_sha256']
    data=retry(lambda:(folder/'internvl_feature.gz').read_bytes());hashed=hashlib.sha256(data).hexdigest();assert hashed==row['feature_sha256']
    features=pickle.loads(gzip.decompress(data));target=retry(lambda:(folder/'trajectory_target.gz').read_bytes())
    target_hash=hashlib.sha256(target).hexdigest();assert target_hash==row['target_sha256'];gt=pickle.loads(gzip.decompress(target))['trajectory']
    assert features['last_hidden_state'].ndim==2 and features['last_hidden_state'].shape[-1]==1536
    assert tuple(features['history_trajectory'].shape)==(4,3) and tuple(features['status_feature'].shape)==(8,) and tuple(features['high_command_one_hot'].shape)==(4,)
    assert all(isinstance(v,torch.Tensor) and v.dtype==torch.float32 and torch.isfinite(v).all() for v in features.values())
    assert tuple(gt.shape)==(8,3) and torch.isfinite(gt).all()
    return features,gt,dict(feature_sha256=hashed,target_sha256=target_hash,feature_identity_sha256=digest(identity),feature_dir=str(folder))
