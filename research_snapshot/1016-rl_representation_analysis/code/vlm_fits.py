"""Reconstruct exploration-only upstream spaces and operator calibrations."""
from common import *
import numpy as np
from functools import lru_cache
from vlm_core import VOUT
from vlm_space import class_geometry,residual,random_bases
from vlm_scan import metadata,save_npz
from scipy.linalg import eigh
from repair_queue_v2 import atomic_unique as atomic

def regular(c):
    r=len(c);return .95*c+.05*max(float(np.trace(c)/r),1e-8)*np.eye(r)

def sqrtm(c,inverse=False):
    e,u=eigh(c,check_finite=False);v=np.maximum(e,1e-10)**(-.5 if inverse else .5);return (u*v)@u.T

def make(spec):
    identity=digest(spec)[:20];path=VOUT/'fits'/(identity+'.npz');meta=path.with_suffix('.json')
    if meta.exists():
        previous=read(meta);assert sha(path)==previous['sha256'];return previous
    proof_path=ROOT/spec.get('cell_proof_path',str((VOUT/'cells'/(spec['cell']+'.json')).relative_to(ROOT)));proof=read(proof_path);assert sha(ROOT/proof['path'])==proof['sha256']
    x=np.load(ROOT/proof['path'],mmap_mode='r');rows,q,exp,fold,sessions,_=metadata();valid=np.isfinite(x[:,0]);m=spec['moment'];assert sha(ROOT/m['path'])==m['sha256']
    with np.load(ROOT/m['path']) as f:mom=[(int(f['ns']),np.array(f['ss']),np.array(f['gs'])),(int(f['nf']),np.array(f['sf']),np.array(f['gf']))]
    centered=spec['centering']=='pooled_centered';g=class_geometry(mom,centered);us,es,uf,ef,rs,rf,ms,mf,center,cov=g;cfg=spec['config'];kind=cfg['kind'];r=cfg['r'];degen=False
    if kind in ['basis_residual','variance_residual']:
        b,s,rank=residual(us,uf,ef,cfg['ks'],cfg['kf'],kind=='variance_residual');assert b is not None and rank>=r;b=b[:,:r]
        if r<len(s):degen=bool(abs(s[r-1]-s[r])<=max(float(s[0]),1.)*1e-8)
        assert not degen,('Repeated singular cutoff',spec)
    elif kind=='success_pca128_shrink_qda':
        r=min(128,rs);b=us[:,:r]
    elif kind in ['success_pca','failure_pca']:b=(us if kind=='success_pca' else uf)[:,:r]
    elif kind=='full':b=np.eye(x.shape[1]);r=x.shape[1]
    elif kind=='random':b=random_bases(x.shape[1],int(digest(dict(cell=spec['cell'],vlm_space_root=20261016))[:16],16))[cfg['replicate']][:,:r]
    else:raise ValueError(kind)
    assert b.shape[1]==r and np.allclose(b.T@b,np.eye(r),atol=1e-6)
    mh=(ms-center)@b;ml=(mf-center)@b
    ch=regular(mom[0][2]/mom[0][0]-np.outer(ms,ms)) if kind=='full' else regular(b.T@(mom[0][2]/mom[0][0]-np.outer(ms,ms))@b)
    cf=regular(mom[1][2]/mom[1][0]-np.outer(mf,mf)) if kind=='full' else regular(b.T@(mom[1][2]/mom[1][0]-np.outer(mf,mf))@b)
    # Above 1024D, full controls avoid an unnecessary dense OT fit. All selected
    # low-dimensional spaces retain the full operator family.
    transport=np.eye(r)
    if r<=1024:
        sh=sqrtm(ch);transport=sh@sqrtm(sh@cf@sh,inverse=True)@sh
    gap=mf-ms;variance=max(float(gap@cov@gap),1e-24);risk_direction=gap/np.sqrt(variance)
    use=exp&valid;qq=np.asarray(q[use]);xx=np.asarray(x[use],dtype=np.float64)
    cross=xx.T@(qq-qq.mean())/len(qq);qc=b.T@cross
    qc=qc/np.maximum(np.diag((ch+cf)*.5),1e-8) if kind=='full' else np.linalg.solve(regular((ch+cf)*.5),qc);qc=qc/max(np.linalg.norm(qc),1e-12)*max(np.linalg.norm(mh-ml),1e-4)
    high=np.flatnonzero(exp&valid&(q>.9));high=sorted(high,key=lambda i:digest(dict(token=rows[i]['token'],prototype_root=20261016)))[:256]
    proto=(np.asarray(x[high],dtype=np.float64)-center)@b
    rng=np.random.default_rng(int(identity,16));haar=np.eye(r) if kind=='full' else np.linalg.qr(rng.standard_normal(b.shape),mode='reduced')[0]
    inv_s=np.linalg.inv(ch) if r<=1024 else np.empty((0,0));inv_f=np.linalg.inv(cf) if r<=1024 else np.empty((0,0))
    arrays=dict(cov_inv_s=inv_s,cov_inv_f=inv_f,basis=b,center=center,mh=mh,mf=ml,transport=transport,scale=np.sqrt(np.diag(ch)),quality_direction=qc,prototypes=proto,haar=haar,risk_center=ms,risk_direction=risk_direction)
    h=save_npz(path,**{k:v.astype('float32') for k,v in arrays.items()});block,group=spec['cell'].split('__',1)
    result=dict(status='PASS',time=stamp(),id=identity,cell=spec['cell'],block=block,group=group,config=cfg,centering=spec['centering'],path=str(path.relative_to(ROOT)),sha256=h,spec=spec,
        source_sha256=proof['sha256'],cell_proof_path=str(proof_path.relative_to(ROOT)),r=r,full_dim=x.shape[1],native_source='full valid exploration only',class_sizes=[mom[0][0],mom[1][0]],continuous_quality_cases=len(qq),quality_preconditioner='diagonal' if kind=='full' else 'full projected covariance',haar_applicable=kind!='full',full_covariance_ot=r<=1024,cutoff_degenerate=degen)
    atomic(meta,result);return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--spec',required=True);args=p.parse_args();setup('vlm_repair/fits');print(json.dumps(make(read(ROOT/args.spec))))
