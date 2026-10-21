"""Frozen-region confirmation. No validation-driven candidate alteration."""
from common import *
import numpy as np
from subspace_scan_math import directions,metrics,configs,noise_metrics
from subspace_scan_cv import mul,endpoint,original_moments,pair_metrics
from subspace_scan_prepare import OUT,name


def cluster_inference(v,y,sessions,pairs=None):
    v=np.asarray(v);y=np.asarray(y,dtype=bool);unique,inv=np.unique(sessions,return_inverse=True);g=len(unique)
    if not len(v) or not y.any() or y.all():return None
    rng=np.random.default_rng(20261016);draws=rng.multinomial(g,np.full(g,1/g),size=500)
    counts=[];sums=[];squares=[]
    for mask in [y,~y]:
        counts.append(np.bincount(inv[mask],minlength=g));sums.append(np.bincount(inv[mask],weights=v[mask],minlength=g));squares.append(np.bincount(inv[mask],weights=v[mask]**2,minlength=g))
    both=(counts[0]>0)&(counts[1]>0)
    contrast=sums[0][both]/counts[0][both]-sums[1][both]/counts[1][both]
    statistic=contrast.sum();units=contrast
    if pairs is not None:
        gap=v[pairs[:,0]]-v[pairs[:,1]];orders=np.where(gap>1e-12,1.,np.where(gap< -1e-12,0.,.5))
        case_inv=inv[pairs[:,0]];units=np.bincount(case_inv,weights=orders-.5,minlength=g);statistic=units.sum()
    # Fixed spaces and hypotheses, session sign flips, one-sided quality ordering.
    exceed=0
    for _ in range(20):
        signs=rng.choice([-1.,1.],size=(1000,len(units)));exceed+=np.count_nonzero(signs@units>=statistic-1e-12)
    p=(1+exceed)/20001
    order=np.argsort(-v,kind='stable');ends=np.r_[np.flatnonzero(np.diff(v[order])!=0),len(v)-1];ys=y[order]
    aucs=[];aps=[]
    for start in range(0,500,25):
        w=draws[start:start+25,inv[order]];tp=np.cumsum(w*ys,axis=1)[:,ends];total=np.cumsum(w,axis=1)[:,ends];fp=total-tp
        denom=tp[:,-1]*fp[:,-1];ok=denom>0
        aucs.extend((np.sum(np.diff(np.c_[np.zeros(len(w)),fp],axis=1)*(tp+np.c_[np.zeros(len(w)),tp[:,:-1]])*.5,axis=1)[ok]/denom[ok]).tolist())
        aps.extend(np.sum(np.diff(np.c_[np.zeros(len(w)),tp],axis=1)/np.maximum(tp[:,-1,None],1)*tp/np.maximum(total,1),axis=1)[ok].tolist())
    nf=draws@counts[0];nh=draws@counts[1];mf=(draws@sums[0])/np.maximum(nf,1);mh=(draws@sums[1])/np.maximum(nh,1)
    vf=(draws@squares[0])/np.maximum(nf,1)-mf**2;vh=(draws@squares[1])/np.maximum(nh,1)-mh**2
    d=(mf-mh)/np.sqrt(np.maximum((vf+vh)*.5,1e-30));ok=(nf>0)&(nh>0)
    result=dict(sessions=g,p_one_sided_signflip=float(p),sign_flips=20000,auc_ci95=np.quantile(aucs,[.025,.975]).tolist(),
        ap_ci95=np.quantile(aps,[.025,.975]).tolist(),standardized_gap_ci95=np.quantile(d[ok],[.025,.975]).tolist())
    if pairs is not None:
        sums_order=np.bincount(case_inv,weights=orders,minlength=g);nn=np.bincount(case_inv,minlength=g)
        boot=(draws@sums_order)/np.maximum(draws@nn,1);result['pair_ordering_ci95']=np.quantile(boot,[.025,.975]).tolist()
    return result


def confirm(task,backend):
    cell=name(task['route'],task['start'],task['step'],task['layer'],task['token']);lock=read(OUT/'FROZEN_CONFIRMATION.json')
    spec=lock['cells'][cell];assert task['selection_sha256']==sha(OUT/'FROZEN_CONFIRMATION.json')
    proof=read(OUT/'CACHE_INDEX.json')['cells'][cell];path=OUT/'cache'/(cell+'.npy');assert sha(path)==proof['sha256'];x=np.load(path,mmap_mode='r')
    route=task['route'];meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'))
    exp=np.array([r['subset']=='exploration' for r in meta]);valid=~exp;sessions=np.array([r['session'] for r in meta]);entries=configs();cellseed=int(digest(dict(cell=cell,root=20261016))[:16],16)
    if route=='r1':q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');fit_mom=[original_moments(task,label) for label in ['high_quality','failure']]
    else:
        q=np.load(OUT/f'cache/r2_a{task["start"]}_scores.npy');use=exp&endpoint(q[0]);a=np.array(x[0,use],dtype=np.float64);scores=q[0,use];ii=np.arange(len(a));hi=a[ii,np.argmax(scores,axis=1)];lo=a[ii,np.argmin(scores,axis=1)]
    result=[];saved=[]
    for centering in ['uncentered','pooled_centered']:
        chosen=[r for r in spec if r['centering']==centering]
        if not chosen:continue
        if route=='r1':w,c,rank=directions(None,None,centering=='pooled_centered',cellseed,moments=fit_mom)
        else:w,c,rank=directions(hi,lo,centering=='pooled_centered',cellseed)
        unavailable=[r for r in chosen if rank[r['index']]['status']!='VALID']
        for selected in unavailable:result.append(dict(**selected,config=entries[selected['index']],rank=rank[selected['index']],status='UNAVAILABLE_REFIT_RANK',P0=None,P1=None,inference_P0=None,inference_P1=None))
        chosen=[r for r in chosen if rank[r['index']]['status']=='VALID']
        if not chosen:continue
        ids=[r['index'] for r in chosen]
        dest=OUT/'confirmation_fits'/f'{cell}_{centering}.npz';dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists()
        with dest.open('xb') as f:np.savez(f,weights=w[:,ids],midpoint=c,indices=np.asarray(ids))
        fitproof=dict(path=str(dest.relative_to(ROOT)),sha256=sha(dest));saved.append(fitproof)
        if route=='r1':
            mask=valid&((q<.7)|(q>.9));pred=mul(x[mask],w[:,ids],c,backend);stat=metrics(pred,q[mask]<.7,sessions[mask])
            for j,selected in enumerate(chosen):
                inference=cluster_inference(pred[:,j],q[mask]<.7,sessions[mask]);result.append(dict(**selected,config=entries[selected['index']],rank=rank[selected['index']],P0=stat[j],P1=None,inference_P0=inference,inference_P1=None,fit=fitproof))
        else:
            preds={};stats={};case_indices={}
            for g in [0,1]:
                # Evaluate fixed exploration P0 space on all held-out endpoint pairs.
                mask=valid&endpoint(q[g]);idx=np.flatnonzero(mask);a=np.array(x[g,mask]).reshape(-1,x.shape[-1]);pred=mul(a,w[:,ids],c,backend)
                labels=q[g,mask].reshape(-1)<.7;pairs=np.stack([np.arange(len(idx))*2+np.argmin(q[g,mask],axis=1),np.arange(len(idx))*2+np.argmax(q[g,mask],axis=1)],1)
                stats[g]=metrics(pred,labels,np.repeat(sessions[mask],2),pairs=pairs);preds[g]=(pred,labels,np.repeat(sessions[mask],2),pairs);case_indices[g]=idx
            for j,selected in enumerate(chosen):
                infer={g:cluster_inference(preds[g][0][:,j],*preds[g][1:]) for g in [0,1]}
                common,idx0,idx1=np.intersect1d(case_indices[0],case_indices[1],return_indices=True)
                a=preds[0][0].reshape(-1,2,len(ids))[idx0,:,j];b=preds[1][0].reshape(-1,2,len(ids))[idx1,:,j]
                noise=noise_metrics(a[:,0]-a[:,1],b[:,0]-b[:,1])
                result.append(dict(**selected,config=entries[selected['index']],rank=rank[selected['index']],P0=stats[0][j],P1=stats[1][j],inference_P0=infer[0],inference_P1=infer[1],noise_consistency=noise,fit=fitproof))
    return dict(status='COMPLETE',time=stamp(),task=task,cell=cell,route=route,selection_sha256=task['selection_sha256'],
        cache_sha256=proof['sha256'],fixed_exploration_only_fits=True,results=result,fits=saved)
