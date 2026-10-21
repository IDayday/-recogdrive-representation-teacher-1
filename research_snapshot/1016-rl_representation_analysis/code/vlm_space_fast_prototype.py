"""UNADOPTED prototype: compact QR-equivalent residual projection with guards.

For B=V Q/S and B.T B=L L.T, the orthogonal basis is B L**(-T).
Its prefix projectors can be applied in coefficient space. Ill-conditioned,
nearly zero or numerically inconsistent pairs use the original dense QR.
"""
from common import *
import numpy as np
from scipy.linalg import eigh,cholesky,solve_triangular
from vlm_space import configs,class_geometry,random_bases,RS

LAST_STATS={}

def pair(us,uf,ef,ks,kf,weighted,gap,cov,stats):
    d=len(gap)
    if ks>us.shape[1] or kf>uf.shape[1] or ks>=d:return {},np.empty(0),0
    a=us[:,:ks];b=uf[:,:kf];v=b-a@(a.T@b)
    if weighted:v=v*np.sqrt(ef[:kf])[None,:]
    gram=v.T@v;e,q=eigh(gram,check_finite=False);e=np.maximum(e[::-1],0);q=q[:,::-1];s=np.sqrt(e)
    tolerance=max(1e-6,float(s[0])*1e-10) if len(s) else 1e-6
    rank=int(np.count_nonzero(s>tolerance));requested=[r for r in RS if r<=rank]
    if not requested:return {},s,rank
    maximum=max(requested);fallback=s[maximum-1]<max(float(s[0])*1e-3,1e-6);reason='condition' if fallback else None
    stats['pairs']+=1
    if not fallback:
        try:
            coeff=q[:,:maximum]/s[None,:maximum]
            inner=coeff.T@(gram@coeff);inner=(inner+inner.T)*.5
            lower=cholesky(inner,lower=True,check_finite=False)
            transformed=solve_triangular(lower,coeff.T,lower=True,check_finite=False).T
            projected_gap=coeff.T@(v.T@gap)
            whitened=solve_triangular(lower,projected_gap,lower=True,check_finite=False)
            cumulative=np.cumsum(transformed*whitened[None,:],axis=1)
            weights=v@cumulative[:,np.asarray(requested)-1]
            # Check the projection's normal equations using the original V.
            residual=coeff.T@(v.T@(weights-gap[:,None]))
            for j,r in enumerate(requested):
                error=np.linalg.norm(residual[:r,j])/max(np.linalg.norm(projected_gap[:r]),1e-20)
                if not np.isfinite(error) or error>1e-8:fallback=True;reason='normal_equation';break
            variances=(weights*(cov@weights)).sum(0)
            if (np.linalg.norm(weights,axis=0)<1e-7).any() or (variances<1e-18).any():fallback=True;reason='near_zero'
        except (np.linalg.LinAlgError,ValueError,FloatingPointError):fallback=True;reason='factorization'
    if fallback:
        # Exact original expression and QR, including its full retained width.
        keep=min(rank,max(RS));basis=v@q[:,:keep]/s[None,:keep]
        if keep:basis=np.linalg.qr(basis,mode='reduced')[0]
        cumulative=np.cumsum(basis*(basis.T@gap)[None,:],axis=1)
        weights=cumulative[:,np.asarray(requested)-1]
        stats['fallback']+=1;stats['fallback_reasons'][reason]=stats['fallback_reasons'].get(reason,0)+1
    else:stats['compact']+=1
    return {r:weights[:,j] for j,r in enumerate(requested)},s,rank

def directions(moments,centered,construction_seed,return_geometry=False):
    global LAST_STATS
    stats=dict(pairs=0,compact=0,fallback=0,fallback_reasons={});LAST_STATS=stats
    entries=configs();d=len(moments[0][1]);m=len(entries)
    weights=np.full((d,m),np.nan);status=np.ones(m,dtype=np.uint8);rank=np.zeros((m,3),dtype=np.uint16);degenerate=np.zeros(m,dtype=bool)
    if min(moments[0][0],moments[1][0])<2:
        result=(weights,np.zeros(d),status,rank,degenerate);return (*result,None) if return_geometry else result
    geometry=class_geometry(moments,centered);us,es,uf,ef,rs,rf,ms,mf,center,cov=geometry;rank[:,:2]=[rs,rf];gap=mf-ms
    randoms=random_bases(d,construction_seed);last_key=None;cached={};s=np.empty(0);rr=0
    for i,c in enumerate(entries):
        kind=c['kind'];r=c['r']
        if kind in ['basis_residual','variance_residual']:
            key=(kind,c['ks'],c['kf'])
            if key!=last_key:cached,s,rr=pair(us,uf,ef,c['ks'],c['kf'],kind=='variance_residual',gap,cov,stats);last_key=key
            rank[i,2]=rr
            if r not in cached:continue
            w=cached[r]
            if r<len(s):degenerate[i]=abs(s[r-1]-s[r])<=max(float(s[0]),1.)*1e-8
        elif kind in ['success_pca','failure_pca']:
            basis=us if kind=='success_pca' else uf
            if r>basis.shape[1]:continue
            w=basis[:,:r]@(basis[:,:r].T@gap);spectrum=es if kind=='success_pca' else ef
            if r<len(spectrum):degenerate[i]=abs(spectrum[r-1]-spectrum[r])<=max(float(spectrum[0]),1.)*1e-8
        elif kind=='random':
            if r>d:continue
            basis=randoms[c['replicate']][:,:r];w=basis@(basis.T@gap)
        else:w=gap
        weights[:,i]=w;status[i]=0
    valid=np.flatnonzero(status==0)
    if len(valid):
        w=weights[:,valid];variance=(w*(cov@w)).sum(0);good=(variance>1e-24)&(np.linalg.norm(w,axis=0)>1e-12)
        weights[:,valid[good]]=w[:,good]/np.sqrt(variance[good]);weights[:,valid[~good]]=np.nan;status[valid[~good]]=2
    result=(weights,(ms+mf)*.5,status,rank,degenerate)
    return (*result,geometry) if return_geometry else result
