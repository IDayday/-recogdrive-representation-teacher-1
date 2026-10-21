"""Broad rank-constrained spaces and vectorized session-aware quality readouts."""
from common import *
import numpy as np
from functools import lru_cache
from scipy.linalg import eigh
from scipy.stats import t as student_t
from vlm_core import VOUT

P=read(VOUT/'PROTOCOL.json');KS=P['ks_kf'];RS=P['r']
METRICS=['auc','weighted_ap','standardized_gap','gap_training_units','session_positive_fraction','session_macro_gap','session_p','sessions_with_both','class_prevalence']

@lru_cache(maxsize=1)
def configs():
    return [dict(kind=kind,ks=ks,kf=kf,r=r,equal=ks==kf) for kind in ['basis_residual','variance_residual'] for ks in KS for kf in KS for r in RS]+[
        dict(kind=kind,ks=None,kf=None,r=r,equal=None) for kind in ['success_pca','failure_pca'] for r in RS]+[
        dict(kind='random',ks=None,kf=None,r=r,replicate=j,equal=None) for r in RS for j in [0,1,2]]+[
        dict(kind='full',ks=None,kf=None,r=None,equal=None)]

def eigen(second):
    e,u=eigh((second+second.T)*.5,check_finite=False);e=np.maximum(e[::-1],0);u=u[:,::-1]
    rank=int(np.count_nonzero(e>max(e[0]*1e-10,1e-20))) if len(e) else 0
    return u[:,:rank],e[:rank],rank

@lru_cache(maxsize=2)
def random_bases(d,construction_seed):
    rng=np.random.default_rng(construction_seed);result={}
    for j in range(3):
        sample=rng.standard_normal((d,min(d,max(RS))))
        result[j]=np.linalg.qr(sample,mode='reduced')[0]
    return result

def class_geometry(moments,centered):
    (ns,ss,gs),(nf,sf,gf)=moments;ms=ss/ns;mf=sf/nf;d=len(ms)
    center=(ss+sf)/(ns+nf) if centered else np.zeros(d)
    us,es,rs=eigen(gs/ns-np.outer(ms,center)-np.outer(center,ms)+np.outer(center,center))
    uf,ef,rf=eigen(gf/nf-np.outer(mf,center)-np.outer(center,mf)+np.outer(center,center))
    cov=.5*(gs/ns-np.outer(ms,ms)+gf/nf-np.outer(mf,mf))
    return us,es,uf,ef,rs,rf,ms,mf,center,cov

def residual(us,uf,ef,ks,kf,weighted=False):
    d=us.shape[0]
    if ks>us.shape[1] or kf>uf.shape[1] or ks>=d:return None,np.empty(0),0
    a=us[:,:ks];b=uf[:,:kf];v=b-a@(a.T@b)
    if weighted:v=v*np.sqrt(ef[:kf])[None,:]
    e,q=eigh(v.T@v,check_finite=False);e=np.maximum(e[::-1],0);q=q[:,::-1];s=np.sqrt(e)
    tolerance=max(1e-6,float(s[0])*1e-10) if len(s) else 1e-6
    rank=int(np.count_nonzero(s>tolerance));keep=min(rank,max(RS))
    basis=v@q[:,:keep]/s[None,:keep]
    if keep:basis=np.linalg.qr(basis,mode='reduced')[0]
    return basis,s,rank

def directions(moments,centered,construction_seed,return_geometry=False):
    entries=configs();d=len(moments[0][1]);m=len(entries)
    weights=np.full((d,m),np.nan);status=np.ones(m,dtype=np.uint8);rank=np.zeros((m,3),dtype=np.uint16);degenerate=np.zeros(m,dtype=bool)
    if min(moments[0][0],moments[1][0])<2:
        result=(weights,np.zeros(d),status,rank,degenerate)
        return (*result,None) if return_geometry else result
    geometry=class_geometry(moments,centered)
    us,es,uf,ef,rs,rf,ms,mf,center,cov=geometry;rank[:,:2]=[rs,rf];gap=mf-ms
    randoms=random_bases(d,construction_seed)
    # Cache one pair at a time rather than retaining hundreds of D x 1024 bases.
    last_key=None;basis=None;s=np.empty(0);rr=0;prefix=None
    for i,c in enumerate(entries):
        kind=c['kind'];r=c['r']
        if kind in ['basis_residual','variance_residual']:
            key=(kind,c['ks'],c['kf'])
            if key!=last_key:
                basis,s,rr=residual(us,uf,ef,c['ks'],c['kf'],kind=='variance_residual');last_key=key
                prefix=np.cumsum(basis*(basis.T@gap)[None,:],axis=1) if basis is not None and basis.shape[1] else None
            rank[i,2]=rr
            if prefix is None or r>rr:continue
            w=prefix[:,r-1]
            if r<len(s):degenerate[i]=abs(s[r-1]-s[r])<=max(float(s[0]),1.)*1e-8
        elif kind in ['success_pca','failure_pca']:
            basis=us if kind=='success_pca' else uf
            if r>basis.shape[1]:continue
            w=basis[:,:r]@(basis[:,:r].T@gap)
            spectrum=es if kind=='success_pca' else ef
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

def metrics(scores,failed,sessions,high_population=None,sample_weight=None):
    """Uniform-within-class sampling: AUROC is unchanged, AP restores population odds.

    Tie precision uses the end of each entire score tie, matching average precision.
    Cases are the units; acquisition sessions give macro contrasts and exploratory p.
    """
    x=np.asarray(scores,dtype=np.float64);y=np.asarray(failed,dtype=bool);sessions=np.asarray(sessions)
    if x.ndim==1:x=x[:,None]
    out=np.full((x.shape[1],len(METRICS)),np.nan);valid=np.flatnonzero(np.isfinite(x).all(0));nf=int(y.sum());nh=int((~y).sum())
    if not nf or not nh:return out
    wh=(high_population/nh) if high_population is not None else 1.
    weight=np.asarray(sample_weight,dtype=np.float64) if sample_weight is not None else np.where(y,1.,wh)
    assert weight.shape==y.shape and (weight>0).all()
    positive_weight=weight[y].sum();negative_weight=weight[~y].sum()
    groups,inv=np.unique(sessions,return_inverse=True);orders=[];counts=[]
    for mask in [y,~y]:
        ii=np.flatnonzero(mask);ii=ii[np.argsort(inv[ii],kind='stable')];unique,starts,ns=np.unique(inv[ii],return_index=True,return_counts=True)
        cc=np.zeros(len(groups));cc[unique]=np.add.reduceat(weight[ii],starts);orders.append((ii,unique,starts));counts.append(cc)
    both=(counts[0]>0)&(counts[1]>0);ng=int(both.sum());rows=np.arange(len(y))[:,None]
    for begin in range(0,len(valid),128):
        cols=valid[begin:begin+128];v=x[:,cols];order=np.argsort(-v,axis=0,kind='stable');sorted_x=np.take_along_axis(v,order,0);ys=y[order]
        sorted_weight=weight[order];tp=np.cumsum(ys*sorted_weight,axis=0,dtype=np.float64);fp=np.cumsum((~ys)*sorted_weight,axis=0,dtype=np.float64)
        ends=np.vstack([sorted_x[:-1]!=sorted_x[1:],np.ones((1,len(cols)),dtype=bool)])
        starts=np.vstack([np.ones((1,len(cols)),dtype=bool),sorted_x[1:]!=sorted_x[:-1]])
        endix=np.minimum.accumulate(np.where(ends,rows,len(y))[::-1],axis=0)[::-1]
        beforeix=np.maximum.accumulate(np.where(starts,rows-1,-1),axis=0)
        pad_fp=np.vstack([np.zeros((1,len(cols))),fp]);fp_end=np.take_along_axis(pad_fp,endix+1,0);fp_before=np.take_along_axis(pad_fp,beforeix+1,0)
        auc=(ys*sorted_weight*(negative_weight-(fp_end+fp_before)*.5)).sum(0)/(positive_weight*negative_weight)
        precision=tp/(tp+fp);ap=(ys*sorted_weight*np.take_along_axis(precision,endix,0)).sum(0)/positive_weight
        means=[np.average(v[mask],axis=0,weights=weight[mask]) for mask in [y,~y]]
        variance=[np.average((v[mask]-mean)**2,axis=0,weights=weight[mask]) for mask,mean in zip([y,~y],means)]
        gap=means[0]-means[1];var=.5*(variance[0]+variance[1]);standard=gap/np.sqrt(np.maximum(var,1e-30))
        sums=[]
        for ii,unique,first in orders:
            total=np.zeros((len(groups),len(cols)));total[unique]=np.add.reduceat(v[ii]*weight[ii,None],first,axis=0);sums.append(total)
        contrasts=sums[0][both]/counts[0][both,None]-sums[1][both]/counts[1][both,None]
        macro=contrasts.mean(0) if ng else np.full(len(cols),np.nan)
        statistic=macro/np.maximum(contrasts.std(0,ddof=1)/np.sqrt(ng),1e-30) if ng>1 else np.zeros(len(cols))
        p=student_t.sf(statistic,max(ng-1,1)) if ng>1 else np.ones(len(cols))
        out[cols]=np.stack([auc,ap,standard,gap,(contrasts>0).mean(0) if ng else np.full(len(cols),np.nan),macro,p,np.full(len(cols),ng),np.full(len(cols),positive_weight/(positive_weight+negative_weight))],1)
    return out
