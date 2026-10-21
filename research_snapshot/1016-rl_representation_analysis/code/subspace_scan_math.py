"""Full-rank residual construction and prespecified cross-session distribution metrics.
No planner import, inference, or intervention. All linear algebra is float64.
"""
import numpy as np
from scipy.linalg import eigh
from scipy.stats import rankdata, t as student_t

KS=[4,8,16,24,32,48,64,128,256]
RS=[2,4,8,16,24,32,48,64]

def full_basis(x,center):
    z=np.asarray(x,dtype=np.float64)-center
    return basis_moments(z.T@z/max(len(z),1))

def basis_moments(second):
    e,u=eigh((second+second.T)*.5,check_finite=False)
    e=np.maximum(e[::-1],0);u=u[:,::-1]
    rank=int(np.count_nonzero(e>max(e[0]*1e-10,1e-20))) if len(e) else 0
    return u[:,:rank],e,rank

def residual(us,uf,ks,kf):
    if ks>us.shape[1] or kf>uf.shape[1]:return None,None,0
    a=us[:,:ks];b=uf[:,:kf];v=b-a@(a.T@b)
    gram=v.T@v
    e,q=eigh((gram+gram.T)*.5,check_finite=False)
    e=np.maximum(e[::-1],0);q=q[:,::-1];s=np.sqrt(e)
    rank=int(np.count_nonzero(s>1e-6));keep=min(rank,max(RS))
    basis=v@q[:,:keep]/s[None,:keep]
    if keep:basis=np.linalg.qr(basis,mode='reduced')[0]
    return basis,s,rank

def configs():
    return [dict(kind='residual',ks=ks,kf=kf,r=r,equal=ks==kf) for ks in KS for kf in KS for r in RS]+[
        dict(kind='random',ks=None,kf=None,r=r,replicate=j,equal=None) for r in RS for j in [0,1,2]]+[
        dict(kind='full',ks=None,kf=None,r=None,equal=None)]

def directions(hi,lo,centered,control_seed,moments=None):
    """Projected mean-gap probe, matching the original observation protocol.
    Center/scale are fitted from training classes only; no ridge/LDA confound.
    """
    hi=np.asarray(hi,dtype=np.float64);lo=np.asarray(lo,dtype=np.float64)
    if moments is None:
        moments=[(len(x),x.sum(0),x.T@x) for x in [hi,lo]]
    (nh,sh,gh),(nf,sf,gf)=moments
    if nh<2 or nf<2:
        d=len(sh);entries=configs()
        return np.full((d,len(entries)),np.nan),np.zeros(d),[dict(rank_success=0,rank_failure=0,residual_rank=0,cutoff_degenerate=False,status='INSUFFICIENT_TRAIN_CLASSES') for _ in entries]
    mh=sh/nh;ml=sf/nf;d=len(mh);gap=ml-mh
    center=(sh+sf)/(nh+nf) if centered else np.zeros(d)
    def eig(n,mean,gram):return basis_moments(gram/n-np.outer(mean,center)-np.outer(center,mean)+np.outer(center,center))
    us,es,rs=eig(nh,mh,gh);uf,ef,rf=eig(nf,ml,gf)
    pooled_cov=(gh/nh-np.outer(mh,mh)+gf/nf-np.outer(ml,ml))*.5
    entries=configs();weights=np.full((d,len(entries)),np.nan);meta=[];cache={}
    rng=np.random.default_rng(control_seed);randoms={}
    for j in [0,1,2]:
        q,z=np.linalg.qr(rng.standard_normal((d,max(RS))),mode='reduced');q*=np.where(np.diag(z)>=0,1.,-1.)
        randoms[j]=q
    for i,c in enumerate(entries):
        info=dict(rank_success=rs,rank_failure=rf,residual_rank=None,cutoff_degenerate=False,status='VALID')
        if c['kind']=='residual':
            key=(c['ks'],c['kf'])
            if key not in cache:cache[key]=residual(us,uf,*key)
            b,s,rank=cache[key];info['residual_rank']=rank
            if b is None or c['r']>rank:info['status']='RANK_INELIGIBLE';meta.append(info);continue
            r=c['r'];b=b[:,:r]
            if r<len(s) and s[r-1]>1e-6:info['cutoff_degenerate']=bool(abs(s[r-1]-s[r])<=max(s[0],1.)*1e-8)
        elif c['kind']=='random':b=randoms[c['replicate']][:,:c['r']]
        else:b=None
        w=gap.copy() if b is None else b@(b.T@gap)
        var=float(w@pooled_cov@w)
        if var<=1e-24 or np.linalg.norm(w)<1e-12:info['status']='CONSTANT_PROBE';meta.append(info);continue
        weights[:,i]=w/np.sqrt(var);meta.append(info)
    midpoint=(mh+ml)*.5
    return weights,midpoint,meta

def metrics(scores,fail,sessions,pairs=None):
    """Columns are failure-oriented, standardized using train classes only.
    Return global AUROC/AP and per-session contrasts. AP uses end-of-tie precision.
    """
    x=np.asarray(scores,dtype=np.float64);y=np.asarray(fail,dtype=bool);sessions=np.asarray(sessions)
    if x.ndim==1:x=x[:,None]
    result=[];valid=np.isfinite(x).all(0)
    nh=int((~y).sum());nf=int(y.sum())
    if not nh or not nf:return [None for _ in range(x.shape[1])] 
    groups,inverse=np.unique(sessions,return_inverse=True)
    sums=[];counts=[]
    for mask in [y,~y]:
        idx=np.flatnonzero(mask);order=np.argsort(inverse[idx],kind='stable');idx=idx[order]
        unique,starts,ns=np.unique(inverse[idx],return_index=True,return_counts=True)
        totals=np.zeros((len(groups),x.shape[1]));totals[unique]=np.add.reduceat(x[idx],starts,axis=0)
        nn=np.zeros(len(groups));nn[unique]=ns;sums.append(totals);counts.append(nn)
    both=(counts[0]>0)&(counts[1]>0)
    contrasts_all=sums[0][both]/counts[0][both,None]-sums[1][both]/counts[1][both,None]
    g=int(both.sum())
    nh=int((~y).sum());nf=int(y.sum())
    if not nh or not nf:return [None for _ in range(x.shape[1])]
    for j in range(x.shape[1]):
        if not valid[j]:result.append(None);continue
        v=x[:,j]
        order=np.argsort(-v,kind='stable');ordered=v[order];ys=y[order]
        ends=np.r_[np.flatnonzero(np.diff(ordered)!=0),len(v)-1];tp=np.cumsum(ys)[ends];fp=ends+1-tp
        area=np.sum(np.diff(np.r_[0.,fp])*(tp+np.r_[0.,tp[:-1]])*.5)/(nf*nh)
        ap=float(np.sum(np.diff(np.r_[0.,tp/nf])*tp/(ends+1)))
        gap=v[y].mean()-v[~y].mean();var=(v[y].var()+v[~y].var())*.5
        contrasts=contrasts_all[:,j]
        statistic=float(contrasts.mean()/max(contrasts.std(ddof=1)/np.sqrt(g),1e-30)) if g>1 else 0.
        entry=dict(auc=float(area),ap=ap,ap_prevalence=nf/len(y),standardized_gap=float(gap/np.sqrt(max(var,1e-30))),
            mean_gap_standardized_training_units=float(gap),sessions_with_both_classes=g,
            session_positive_fraction=float(np.mean(contrasts>0)) if g else None,
            session_macro_gap=float(contrasts.mean()) if g else None,
            exploratory_p=float(student_t.sf(statistic,max(g-1,1))) if g>1 else 1.)
        if pairs is not None:
            delta=v[pairs[:,0]]-v[pairs[:,1]]
            orders=np.where(delta>1e-12,1.,np.where(delta< -1e-12,0.,.5))
            entry['pair_ordering']=float(orders.mean()) if len(orders) else None
            entry['pairs']=len(orders)
        result.append(entry)
    return result

def noise_metrics(delta0,delta1):
    """Order agreement remains meaningful when rank correlation is undefined for constants."""
    from scipy.stats import spearmanr
    a=np.asarray(delta0);b=np.asarray(delta1);rho=None
    if len(a)>1 and np.ptp(a)>1e-12 and np.ptp(b)>1e-12:
        v=float(spearmanr(a,b).statistic)
        if np.isfinite(v):rho=v
    sa=np.where(a>1e-12,1,np.where(a< -1e-12,-1,0));sb=np.where(b>1e-12,1,np.where(b< -1e-12,-1,0))
    agree=float(np.mean(np.where((sa==0)|(sb==0),.5,(sa==sb).astype(float)))) if len(a) else None
    return dict(common_endpoint_pairs=len(a),branch_score_delta_spearman=rho,common_branch_order_agreement=agree)
