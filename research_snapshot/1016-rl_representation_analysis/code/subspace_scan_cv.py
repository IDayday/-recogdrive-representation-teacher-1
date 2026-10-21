"""Session-cross-fitted expanded scan; held-out validation is never evaluated here."""
from common import *
import numpy as np
from subspace_scan_math import configs,directions,metrics,noise_metrics
from subspace_scan_prepare import OUT,name


def fold_ids(meta):
    return np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in meta])

def endpoint(q):return ((q[:,0]<.7)&(q[:,1]>.9))|((q[:,1]<.7)&(q[:,0]>.9))

def mul(x,w,midpoint,backend):
    if backend=='cpu_float64':return (np.asarray(x,dtype=np.float64)-midpoint)@w
    import torch
    with torch.no_grad():
        a=torch.tensor(x,dtype=torch.float64,device='cuda');b=torch.tensor(w,dtype=torch.float64,device='cuda')
        c=torch.tensor(midpoint,dtype=torch.float64,device='cuda');return ((a-c)@b).cpu().numpy()

def moments(x):return (len(x),x.sum(0),x.T@x)

def original_moments(task,label):
    src='representations' if task['layer']<18 else 'dit_output'
    f=ROOT/'analysis/natural_route1_v1/moments'/('exploration__'+label)
    def get(field):
        v=np.load(f/(src+'_'+field+'.npy'),mmap_mode='r')
        return np.array(v[task['step'],task['layer'],task['token']] if src=='representations' else v[task['step'],task['token']],dtype=np.float64)
    return int(np.load(f/'n.npy')),get('sum'),get('gram')

def subtract(a,b):return tuple(x-y for x,y in zip(a,b))

def pair_metrics(pred,q,mask,sessions):
    idx=np.flatnonzero(mask);s=pred[idx].reshape(-1,pred.shape[-1]);labels=q[idx].reshape(-1)<.7
    paired=np.stack([np.arange(len(idx))*2+np.argmin(q[idx],axis=1),np.arange(len(idx))*2+np.argmax(q[idx],axis=1)],1)
    return metrics(s,labels,np.repeat(sessions[idx],2),pairs=paired)

def scan(task,backend='cpu_float64'):
    route=task['route'];cell=name(route,task['start'],task['step'],task['layer'],task['token'])
    path=OUT/'cache'/(cell+'.npy');proof=read(OUT/'CACHE_INDEX.json')['cells'][cell]
    assert sha(path)==proof['sha256'];x=np.load(path,mmap_mode='r');assert list(x.shape)==proof['shape']
    meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'))
    exp=np.array([r['subset']=='exploration' for r in meta]);fold=fold_ids(meta);sessions=np.array([r['session'] for r in meta]);n=len(meta)
    candidates=configs();m=len(candidates);results=[];cellseed=int(digest(dict(cell=cell,root=20261016))[:16],16)
    if route=='r1':
        q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');use=exp&((q<.7)|(q>.9));indices=np.flatnonzero(use)
        total=[original_moments(task,label) for label in ['high_quality','failure']]
        # Verify a raw-cache tile against the existing full sufficient statistics before reuse.
        for j,mask in enumerate([exp&(q>.9),exp&(q<.7)]):
            tile=np.asarray(x[mask,:8],dtype=np.float64);assert len(tile)==total[j][0]
            assert np.allclose(tile.sum(0),total[j][1][:8],rtol=1e-9,atol=1e-6)
            assert np.allclose(tile.T@tile,total[j][2][:8,:8],rtol=1e-9,atol=1e-6)
    else:q=np.load(OUT/f'cache/r2_a{task["start"]}_scores.npy');indices=np.flatnonzero(exp)
    fold_moments=[];full_moment_verified=False
    if route=='r1':
        held_moments=[]
        for k in range(5):
            held_moments.append([moments(np.asarray(x[mask],dtype=np.float64)) for mask in [exp&(fold==k)&(q>.9),exp&(fold==k)&(q<.7)]])
        for group in range(2):
            for field in range(3):
                reconstructed=sum(v[group][field] for v in held_moments)
                assert np.allclose(reconstructed,total[group][field],rtol=1e-9,atol=1e-6),(cell,group,field,'full moment mismatch')
        full_moment_verified=True
        fold_moments=[[subtract(a,b) for a,b in zip(total,held)] for held in held_moments]
    else:
        good=exp&endpoint(q[0]);a=np.asarray(x[0,good],dtype=np.float64);scores=q[0,good];ii=np.arange(len(a))
        hi=a[ii,np.argmax(scores,axis=1)];lo=a[ii,np.argmin(scores,axis=1)];pair_folds=fold[good]
        totals=[moments(hi),moments(lo)]
        fold_moments=[[subtract(total,moments(a[pair_folds==k])) for total,a in zip(totals,[hi,lo])] for k in range(5)]
    for centered in [False,True]:
        oof=np.full((len(indices),m),np.nan) if route=='r1' else np.full((2,n,2,m),np.nan)
        fold_records=[];all_meta=[]
        for k in range(5):
            train=exp&(fold!=k);test=exp&(fold==k)
            if route=='r1':
                testmask=use&(fold==k);fit_mom=fold_moments[k]
                w,c,rank_meta=directions(None,None,centered,cellseed,moments=fit_mom)
                pred=mul(x[testmask],w,c,backend);at=np.flatnonzero(fold[indices]==k);oof[at]=pred
                stat=metrics(pred,q[testmask]<.7,sessions[testmask])
                fold_records.append(dict(fold=k,P0=stat,P1=None))
            else:
                w,c,rank_meta=directions(None,None,centered,cellseed,moments=fold_moments[k])
                for g in [0,1]:oof[g,test]=mul(np.asarray(x[g,test]).reshape(-1,x.shape[-1]),w,c,backend).reshape(int(test.sum()),2,m)
                fold_records.append(dict(fold=k,**{f'P{g}':pair_metrics(oof[g],q[g],test&endpoint(q[g]),sessions) for g in [0,1]}))
            all_meta.append(rank_meta)
        if route=='r1':pooled=metrics(oof,q[indices]<.7,sessions[indices]);p1=None
        else:
            pooled=pair_metrics(oof[0],q[0],exp&endpoint(q[0]),sessions);p1=pair_metrics(oof[1],q[1],exp&endpoint(q[1]),sessions)
        for i,cfg in enumerate(candidates):
            ranks=[r[i] for r in all_meta];valid=all(r['status']=='VALID' for r in ranks)
            record=dict(config=cfg,centering='pooled_centered' if centered else 'uncentered',status='VALID' if valid else 'INELIGIBLE_IN_CV',
                folds=[dict(fold=r['fold'],P0=r['P0'][i],P1=r['P1'][i] if r['P1'] else None,rank=ranks[j]) for j,r in enumerate(fold_records)],
                P0=pooled[i],P1=p1[i] if p1 else None,cutoff_degenerate_any_fold=any(r['cutoff_degenerate'] for r in ranks))
            if valid and pooled[i]:
                areas=[r['P0'][i]['auc'] for r in fold_records if r['P0'][i]]
                record['auc_fold_min']=float(min(areas));record['auc_fold_std']=float(np.std(areas));record['auc_fold_mean']=float(np.mean(areas))
            if route=='r2' and valid:
                common=exp&endpoint(q[0])&endpoint(q[1]);d0=oof[0,common,0,i]-oof[0,common,1,i];d1=oof[1,common,0,i]-oof[1,common,1,i]
                record['noise_consistency']=dict(**noise_metrics(d0,d1),P0_ordering=pooled[i]['pair_ordering'] if pooled[i] else None,P1_ordering=p1[i]['pair_ordering'] if p1[i] else None)
            results.append(record)
    return dict(status='COMPLETE',time=stamp(),task=task,cell=cell,backend=backend,cache_sha256=proof['sha256'],
        heldout_validation_evaluated=False,full_moment_reuse_verified_all_dimensions=full_moment_verified,exploration_sessions=len(set(sessions[exp])),search=results)
