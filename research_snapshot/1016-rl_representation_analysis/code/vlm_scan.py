"""Full-statistics, session-cross-fitted broad VLM scan; no held-out/test tuning."""
from common import *
import argparse
import io
import uuid
from functools import lru_cache
import numpy as np
from scipy.linalg import cho_factor,cho_solve
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
from vlm_space import configs,directions,metrics,METRICS

def save_npz(path,**arrays):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        with np.load(path,allow_pickle=False) as previous:
            assert set(previous.files)==set(arrays)
            for name,value in arrays.items():assert np.array_equal(previous[name],value,equal_nan=True),name
        return sha(path)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('wb') as f:np.savez(f,**arrays)
    tmp.replace(path);return sha(path)

@lru_cache(maxsize=1)
def metadata():
    rows=read(ROOT/'manifests/natural_s0.json');q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy',mmap_mode='r');exp=np.array([r['subset']=='exploration' for r in rows])
    fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);sessions=np.array([r['session'] for r in rows])
    high=np.flatnonzero(exp&(q>.9));high=np.array(sorted(high,key=lambda i:digest(dict(token=rows[i]['token'],vlm_cv_eval=20261016))))
    return rows,q,exp,fold,sessions,high

def moment(x,mask):
    a=np.asarray(x[mask],dtype=np.float64)
    return len(a),a.sum(0),a.T@a

def subtract(a,b):return tuple(x-y for x,y in zip(a,b))

def number(value):return float(value) if np.isfinite(value) else None

def metric_dict(values):return {key:number(v) for key,v in zip(METRICS,values)}

def extra_readouts(x,mom,geometry):
    """Energy and shrink-QDA preserve variance-only candidates beside mean-gap probes."""
    if geometry is None:return np.full((len(x),2),np.nan)
    us,es,uf,ef,rs,rf,ms,mf,center,cov=geometry;a=np.asarray(x,dtype=np.float64);d=a.shape[1]
    ns,ss,gs=mom[0];nf,sf,gf=mom[1]
    e_s=np.trace(gs)/ns-2*ms@center+center@center;e_f=np.trace(gf)/nf-2*mf@center+center@center
    energy=np.square(a-center).sum(1)*(1. if e_f>=e_s else -1.)
    r=min(128,rs);basis=us[:,:r];z=a@basis;means=[ms@basis,mf@basis];covs=[]
    for n,mean,gram in [(ns,ms,gs),(nf,mf,gf)]:
        c=basis.T@(gram/n-np.outer(mean,mean))@basis
        scale=max(float(np.trace(c)/max(r,1)),1e-10);c=.95*c+.05*scale*np.eye(r);covs.append(c)
    likelihood=[]
    for mean,c in zip(means,covs):
        cf=cho_factor(c,check_finite=False);diff=z-mean
        likelihood.append(-.5*((diff*cho_solve(cf,diff.T,check_finite=False).T).sum(1)+2*np.log(np.diag(cf[0])).sum()))
    return np.stack([energy,likelihood[1]-likelihood[0]],1)

def scan(cell,output=None):
    proof=read(VOUT/'cells'/(cell+'.json'));path=ROOT/proof['path'];assert sha(path)==proof['sha256'];x=np.load(path,mmap_mode='r')
    rows,q,exp,fold,sessions,high_order=metadata();valid=np.isfinite(x[:,0]);extreme=(q<.7)|(q>.9);fit=exp&valid&extreme
    ev=exp&valid&(q<.7);ev[high_order[valid[high_order]][:8192]]=True;indices=np.flatnonzero(ev)
    destination=output or VOUT/'scan/results'/(cell+'.json')
    if destination.exists():
        previous=read(destination);assert previous['source_sha256']==proof['sha256']
        for array_path,array_sha in [('array_path','array_sha256'),('moment_path','moment_sha256')]:
            if array_path in previous:assert sha(ROOT/previous[array_path])==previous[array_sha]
        return previous
    if not fit.any() or min(int((fit&(q<.7)).sum()),int((fit&(q>.9)).sum()))<10:
        result=dict(status='INELIGIBLE',time=stamp(),cell=cell,reason='insufficient valid extreme classes',valid_cases=int(valid.sum()),source_sha256=proof['sha256']);atomic(destination,result);return result
    held=[]
    for k in range(5):held.append([moment(x,fit&(fold==k)&mask) for mask in [q>.9,q<.7]])
    totals=[tuple(sum(h[group][field] for h in held) for field in range(3)) for group in range(2)]
    moment_path=VOUT/'moments'/(cell+'.npz')
    moment_sha=save_npz(moment_path,ns=totals[0][0],nf=totals[1][0],ss=totals[0][1],sf=totals[1][1],gs=totals[0][2],gf=totals[1][2])
    entries=configs();m=len(entries);all_metrics=np.full((2,6,m,len(METRICS)),np.nan);status=np.zeros((2,5,m),dtype=np.uint8)
    ranks=np.zeros((2,5,m,3),dtype=np.uint16);degenerate=np.zeros((2,5,m),dtype=bool);extras=np.full((2,6,2,len(METRICS)),np.nan)
    locations=np.full(len(rows),-1,dtype=int);locations[indices]=np.arange(len(indices));seed_value=int(digest(dict(cell=cell,vlm_space_root=20261016))[:16],16)
    best=[];noise_records=[];base=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')[:,:,0,0]
    assert np.array_equal(base[0],q)
    for centered in [False,True]:
        cc=int(centered);oof=np.full((len(indices),m),np.nan);extra_oof=np.full((len(indices),2),np.nan)
        for k in range(5):
            train_mom=[subtract(total,part) for total,part in zip(totals,held[k])]
            w,c,s,rank,degen,geometry=directions(train_mom,centered,seed_value,return_geometry=True);status[cc,k]=s;ranks[cc,k]=rank;degenerate[cc,k]=degen
            test=ev&(fold==k);at=locations[np.flatnonzero(test)];good=np.flatnonzero(s==0)
            a=np.asarray(x[test],dtype=np.float64);pred=(a-c)@w[:,good];oof[np.ix_(at,good)]=pred
            high_pop=int((fit&(fold==k)&(q>.9)).sum());all_metrics[cc,k,good]=metrics(pred,q[test]<.7,sessions[test],high_population=high_pop)
            extra_oof[at]=extra_readouts(a,train_mom,geometry);extras[cc,k]=metrics(extra_oof[at],q[test]<.7,sessions[test],high_population=high_pop)
        eligible=(status[cc]==0).all(0);oof[:,~eligible]=np.nan
        high_pop=int((fit&(q>.9)).sum());all_metrics[cc,5]=metrics(oof,q[indices]<.7,sessions[indices],high_population=high_pop)
        extras[cc,5]=metrics(extra_oof,q[indices]<.7,sessions[indices],high_population=high_pop)
        pooled=all_metrics[cc,5];minimum=np.nanmin(all_metrics[cc,:5,:,0],axis=0);spread=np.nanstd(all_metrics[cc,:5,:,0],axis=0)
        # Preserve dimensional neighborhoods from each construction, equality and rank band.
        chosen=set()
        for kind in ['basis_residual','variance_residual','success_pca','failure_pca','full']:
            for equal in ([True,False] if kind.endswith('residual') else [None]):
                for lo,hi in [(0,16),(17,128),(129,99999)]:
                    group=[i for i,cfg in enumerate(entries) if cfg['kind']==kind and cfg.get('equal')==equal and lo<=(cfg['r'] or 0)<=hi and eligible[i] and np.isfinite(pooled[i,0])]
                    group.sort(key=lambda i:(pooled[i,0]-.25*spread[i],minimum[i],pooled[i,2]),reverse=True)
                    chosen.update(group[:3])
        chosen=sorted(chosen);s0_weights=np.where(q[indices]<.7,1.,high_pop/max(int((q[indices]>.9).sum()),1))
        for i in chosen:
            values=pooled[i];record=dict(config_index=i,config=entries[i],centering='pooled_centered' if centered else 'uncentered',metrics=metric_dict(values),
                auc_fold_min=number(minimum[i]),auc_fold_std=number(spread[i]),cutoff_degenerate_any=bool(degenerate[cc,:,i].any()),ranks=ranks[cc,:,i].tolist())
            noise=[]
            for j in [1,2]:
                use=(base[j,indices]<.7)|(base[j,indices]>.9)
                stat=metrics(oof[use,i],base[j,indices[use]]<.7,sessions[indices[use]],sample_weight=s0_weights[use])[0]
                noise.append(dict(seed_index=j,metrics=metric_dict(stat)))
            record['other_sampling_seeds']=noise;best.append(record)
        for i,name in enumerate(['full_energy','success_pca128_shrink_qda']):
            best.append(dict(secondary_readout=name,config=dict(kind=name,r=None if i==0 else 128,ks=None,kf=None,equal=None),centering='pooled_centered' if centered else 'uncentered',metrics=metric_dict(extras[cc,5,i]),
                auc_fold_min=number(np.nanmin(extras[cc,:5,i,0])),auc_fold_std=number(np.nanstd(extras[cc,:5,i,0])),cutoff_degenerate_any=False))
    arrays=VOUT/'scan/arrays'/(cell+'.npz');array_sha=save_npz(arrays,metrics=all_metrics,status=status,ranks=ranks,cutoff_degenerate=degenerate,secondary_metrics=extras,evaluation_indices=indices,fold_ids=fold[indices])
    result=dict(status='COMPLETE',time=stamp(),cell=cell,source=proof,source_sha256=proof['sha256'],dimension=x.shape[1],valid_cases=int(valid.sum()),
        training_class_sizes=[int(t[0]) for t in totals],cv_evaluation_cases=len(indices),eval_policy='all valid exploration S0 failures + up to 8192 uniform valid exploration S0 highs per cell; inverse-probability weighted AP and secondary-seed metrics',
        configs=len(entries),eligible_by_center=[int((status[c]==0).all(0).sum()) for c in [0,1]],metric_evaluable_by_center=[int(np.isfinite(all_metrics[c,5,:,0]).sum()) for c in [0,1]],metric_fields=METRICS,
        array_path=str(arrays.relative_to(ROOT)),array_sha256=array_sha,moment_path=str(moment_path.relative_to(ROOT)),moment_sha256=moment_sha,
        shortlisted=best,heldout_validation_evaluated=False,test_accessed=False)
    atomic(destination,result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cell',required=True);args=p.parse_args();setup('vlm_repair/scan_single');scan(args.cell)
