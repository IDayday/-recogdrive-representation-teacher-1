"""Gaussian direction / Haar subspace nulls without consuming the native model sampling stream."""
from common import *
import numpy as np

def predict_control(editor,chain,arm):
    if not arm.get('gaussian_null'):return editor.predict(chain,arm)
    import torch
    assert arm['method']=='mean' and arm['steps']==[4] and 'multi_layers' not in arm and 'multi_steps' not in arm
    f=editor.load(4,arm['layer'],arm['k']);saved={}
    try:
        for tok in arm['tokens']:
            p=f'{arm["source"]}_{tok}_';b=f[p+'b'];delta=f[p+'mh']-f[p+'ml']
            value=int(digest(dict(root=20261016,replicate=arm['control_seed'],layer=arm['layer'],token=tok))[:16],16)
            rng=np.random.default_rng(value)
            if arm['gaussian_null']=='direction':
                u=rng.standard_normal(b.shape[1]);u/=np.linalg.norm(u)
                vector=torch.tensor(u,device=b.device,dtype=b.dtype)*delta.norm()
                saved[p+'ml']=f[p+'ml'];f[p+'ml']=f[p+'mh']-vector
            elif arm['gaussian_null']=='subspace':
                q,r=np.linalg.qr(rng.standard_normal(tuple(b.shape)),mode='reduced')
                q*=np.where(np.diag(r)>=0,1.,-1.)
                saved[p+'b']=b;f[p+'b']=torch.tensor(q,device=b.device,dtype=b.dtype)
            else:raise ValueError(arm['gaussian_null'])
        return editor.predict(chain,arm)
    finally:
        for key,value in saved.items():f[key]=value

def prepare():
    root=ROOT/'repair_v1';parent=read(root/'MATCHED_VALIDATION_ENQUEUED.json')['parent'];arms=[]
    for kind in ['direction','subspace']:
        for replicate in [0,1,2]:
            a=dict(parent,gaussian_null=kind,control_seed=replicate,control=True,matched_parent=parent['id'])
            a.pop('id');a['id']='gaussian_'+kind+'_'+digest(a)[:12];arms.append(a)
    path=root/'true_random_arms.json';assert not path.exists();atomic(path,arms)
    atomic(root/'TRUE_RANDOM_PROTOCOL.json',dict(status='FROZEN',time=stamp(),parent=parent,arms=arms,
        reason='Retain original deterministic sin/QR non-task controls; add genuine Gaussian direction and Haar subspace controls.',
        parent_selected_on='exploration screen only',training=False,native_rng_consumed=False,
        gaussian_seed_root=20261016,matching='same site, alpha, per-token pre-cap and post-cap hidden norm as parent',
        selection_candidate=False))

if __name__=='__main__':setup('repair/true_random_prepare');prepare()
