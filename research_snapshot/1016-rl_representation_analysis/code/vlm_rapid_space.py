"""Prespecified fast first pass: full dimensional range, all cells; full residual grid remains separate."""
from vlm_space import P,RS,METRICS,metrics,class_geometry,random_bases
import numpy as np
from functools import lru_cache

@lru_cache(maxsize=1)
def configs():
    return [dict(kind=k,ks=None,kf=None,r=r,equal=None) for k in ['success_pca','failure_pca'] for r in RS]+[dict(kind='random',ks=None,kf=None,r=r,replicate=j,equal=None) for r in RS for j in [0,1,2]]+[dict(kind='full',ks=None,kf=None,r=None,equal=None)]

def directions(moments,centered,construction_seed,return_geometry=False):
    g=class_geometry(moments,centered);us,es,uf,ef,rs,rf,ms,mf,center,cov=g;gap=mf-ms;entries=configs();d=len(gap)
    w=np.full((d,len(entries)),np.nan);status=np.ones(len(entries),dtype=np.uint8);ranks=np.zeros((len(entries),3),dtype=np.uint16);ranks[:,:2]=[rs,rf];deg=np.zeros(len(entries),dtype=bool);randoms=random_bases(d,construction_seed)
    for i,c in enumerate(entries):
        r=c['r'];kind=c['kind']
        if kind=='full':v=gap
        else:
            basis=us if kind=='success_pca' else uf if kind=='failure_pca' else randoms[c['replicate']]
            if r>basis.shape[1]:continue
            v=basis[:,:r]@(basis[:,:r].T@gap)
            if kind!='random':
                spectrum=es if kind=='success_pca' else ef
                if r<len(spectrum):deg[i]=abs(spectrum[r-1]-spectrum[r])<=max(float(spectrum[0]),1.)*1e-8
        w[:,i]=v;status[i]=0
    ix=np.flatnonzero(status==0);z=w[:,ix];variance=(z*(cov@z)).sum(0);valid=(variance>1e-24)&(np.linalg.norm(z,axis=0)>1e-12)
    w[:,ix[valid]]=z[:,valid]/np.sqrt(variance[valid]);w[:,ix[~valid]]=np.nan;status[ix[~valid]]=2
    out=(w,(ms+mf)*.5,status,ranks,deg)
    return (*out,g) if return_geometry else out
