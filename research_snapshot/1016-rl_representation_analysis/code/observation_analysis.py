"""Train-only exact low-dimensional observation; all fitting uses exploration P0.

Route two runs before route one. Held-out P0/P1 use the SAME fitted bases and
directions. No parameter intervention, test-set access, or validation selection.
"""
from common import *
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import numpy as np


def make_cache(run,out):
    from paired_acceptance import load_records
    records=load_records(run,'formal')
    assert len(records)==45760
    refs=read(ROOT/'runs/gt_reference_full_20261016_v2/references.json')
    refs=sorted(refs,key=lambda r:r['token']);n=len(refs);by={r['token']:i for i,r in enumerate(refs)}
    paths={g:{} for g in [0,1]};scores=np.zeros((2,n,2));seen=set()
    for r in records:
        if r['start_t']!=0:continue
        i=by[r['token']];g=r['noise_group'];b=r['branch_index'];key=(g,i,b)
        assert key not in seen;seen.add(key)
        scores[g,i,b]=r['score']['score'];paths[g][i]=r['array_path']
    assert len(seen)==2*n*2
    cache=out/'cache';cache.mkdir(parents=True,exist_ok=True)
    for g in [0,1]:
        x=np.lib.format.open_memmap(cache/f'hidden_P{g}.npy',mode='w+',dtype=np.float32,shape=(n,2,18,8,384))
        z=np.lib.format.open_memmap(cache/f'output_P{g}.npy',mode='w+',dtype=np.float32,shape=(n,2,8,512))
        for i in range(n):
            with np.load(paths[g][i],allow_pickle=False) as data:
                assert data['timesteps'].tolist()==[0]
                x[i]=data['representations'][:,0];z[i]=data['dit_output'][:,0]
            if i%256==0:print(json.dumps(dict(stage='cache',noise_group=g,completed=i,total=n)),flush=True)
        x.flush();z.flush();del x,z
    np.save(cache/'scores.npy',scores)
    atomic(cache/'metadata.json',[{k:r[k] for k in ['token','session','subset','primary_mode']} for r in refs])
    atomic(cache/'COMPLETE.json',dict(status='COMPLETE',scenes=n,time=stamp(),start_t=0,source_run=run))
    return records


def basis_svd(x,maxdim=32):
    """Exact SVD via the smaller symmetric Gram matrix, in float64."""
    from scipy.linalg import eigh
    x=np.asarray(x,dtype=np.float64)
    if min(x.shape)==0:return np.zeros((x.shape[1],0)),np.zeros(0)
    if len(x)<x.shape[1]:
        vals,v=eigh(x@x.T,check_finite=False)
        order=np.argsort(vals)[::-1];vals=np.maximum(vals[order],0);v=v[:,order]
        valid=vals>max(float(vals[0])*1e-10,1e-20)
        k=min(maxdim,int(valid.sum()))
        u=x.T@v[:,:k]/np.sqrt(vals[:k])[None,:] if k else np.zeros((x.shape[1],0))
    else:
        vals,v=eigh(x.T@x,check_finite=False)
        order=np.argsort(vals)[::-1];vals=np.maximum(vals[order],0);v=v[:,order]
        k=min(maxdim,int((vals>max(float(vals[0])*1e-10,1e-20)).sum()))
        u=v[:,:k]
    return u,vals


def endpoint_mask(q):
    return ((q[:,0]<.7)&(q[:,1]>.9))|((q[:,1]<.7)&(q[:,0]>.9))


def paired_arrays(x,q,mask):
    a=x[mask];s=q[mask];hi=np.argmax(s,axis=1);lo=1-hi;rows=np.arange(len(a))
    return a[rows,hi],a[rows,lo]


def auc(scores,labels):
    from scipy.stats import rankdata
    labels=np.asarray(labels,dtype=bool);n=int(labels.sum());m=int((~labels).sum())
    if n==0 or m==0:return None
    return float((rankdata(scores)[labels].sum()-n*(n+1)/2)/(n*m))


def cluster_test(values,sessions):
    """Pair ordering values in {0, .5, 1}; resample/sign-flip entire sessions."""
    sessions=np.asarray(sessions);values=np.asarray(values,dtype=float)
    unique,inverse=np.unique(sessions,return_inverse=True);groups=len(unique)
    if not len(values):return dict(n=0,sessions=0,ordering=None,ci95=None,p=None)
    totals=np.bincount(inverse,weights=values,minlength=groups);counts=np.bincount(inverse,minlength=groups)
    rng=np.random.default_rng(20261016);draw=rng.integers(groups,size=(500,groups))
    bootstrap=totals[draw].sum(1)/counts[draw].sum(1)
    centered=totals-.5*counts
    signs=rng.choice([-1.,1.],size=(1999,groups))
    null=signs@centered;observed=abs(centered.sum())
    p=float((1+np.count_nonzero(np.abs(null)>=observed-1e-12))/2000)
    return dict(n=len(values),sessions=groups,ordering=float(values.mean()),
                ci95=np.quantile(bootstrap,[.025,.975]).tolist(),p=p)


def evaluate(x,q,mask,sessions,modes,direction,center):
    hi,lo=paired_arrays(x,q,mask)
    gap=(hi-lo)@direction
    ordering=np.where(gap>1e-12,1.,np.where(gap< -1e-12,0.,.5))
    test=cluster_test(ordering,np.asarray(sessions)[mask])
    all_scores=(x-center)@direction
    endpoint=(q<.7)|(q>.9)
    bymode={}
    for mode in sorted(set(modes)):
        m=np.asarray(modes)[mask]==mode
        if m.any():bymode[mode]=dict(n=int(m.sum()),ordering=float(ordering[m].mean()))
    return dict(**test,mean_pair_projection_gap=float(gap.mean()) if len(gap) else None,
                pair_projection_gap_std=float(gap.std()) if len(gap) else None,
                all_endpoint_auc=auc(all_scores[endpoint],q[endpoint]>.9),
                within_source_auc={s:auc(all_scores[:,b][endpoint[:,b]],q[:,b][endpoint[:,b]]>.9)
                                   for b,s in enumerate(['baseline_failure','GT'])},by_baseline_mode=bymode)


def residual_basis(high,low,center,k=8):
    us,es=basis_svd(high-center);uf,ef=basis_svd(low-center)
    k=min(k,us.shape[1],uf.shape[1]);us=us[:,:k];uf=uf[:,:k]
    if k==0:return np.zeros((high.shape[1],0)),dict(k=0,residual_singular_values=[])
    r=uf-us@(us.T@uf)
    v,s,_=np.linalg.svd(r,full_matrices=False)
    keep=s>1e-6
    return v[:,keep],dict(k=k,residual_singular_values=s.tolist(),effective_residual_rank=int(keep.sum()),
        residual_energy=float((s*s).sum()),subspace_overlap=float(np.linalg.norm(us.T@uf,'fro')**2/k),
        high_top8_energy=float(es[:k].sum()/max(es.sum(),1e-30)),low_top8_energy=float(ef[:k].sum()/max(ef.sum(),1e-30)))


def fit_cell(job):
    from scipy.stats import spearmanr
    out,layer,token=job;out=Path(out);cache=out/'cache';metadata=read(cache/'metadata.json')
    train=np.asarray([r['subset']=='exploration' for r in metadata]);valid=~train
    sessions=np.asarray([r['session'] for r in metadata]);modes=np.asarray([r['primary_mode'] for r in metadata])
    scores=np.load(cache/'scores.npy');x={}
    for g in [0,1]:
        if layer<18:x[g]=np.asarray(np.load(cache/f'hidden_P{g}.npy',mmap_mode='r')[:,:,layer,token,:],dtype=np.float64)
        else:x[g]=np.asarray(np.load(cache/f'output_P{g}.npy',mmap_mode='r')[:,:,token,:],dtype=np.float64)
    q=scores[0];match=train&endpoint_mask(q);hi,lo=paired_arrays(x[0],q,match)
    cell=f'layer{layer:02d}_token{token}';base=dict(cell=cell,layer=layer,token=token,dim=x[0].shape[-1],
        train_pairs=int(match.sum()),train_pair_sessions=len(set(sessions[match])),
        train_global_high=int((q[train]>.9).sum()),train_global_fail=int((q[train]<.7).sum()))
    if len(hi)<2:
        atomic(out/'cells'/f'{cell}.json',dict(**base,status='INSUFFICIENT_TRAIN_PAIRS'));return base
    delta=hi-lo;u,e=basis_svd(delta);k=min(8,u.shape[1]);b=u[:,:k]
    mean=delta.mean(0);direction=b@(b.T@mean)
    norm=np.linalg.norm(direction)
    if norm>1e-12:direction/=norm
    pooled=np.concatenate([hi,lo]).mean(0)
    arrays=dict(difference_basis=u,difference_spectrum=e,paired_mean_difference=mean,
                paired_pooled_center=pooled,difference_direction=direction)
    tests={};variants=[]
    # Primary route: quality-matched within-scene differences; the same basis and direction on both held-out banks.
    train_result=evaluate(x[0][train],q[train],endpoint_mask(q[train]),sessions[train],modes[train],direction,pooled)
    primary=dict(name='paired_difference_svd',k=k,train=train_result,
        top8_energy=float(e[:k].sum()/max(e.sum(),1e-30)),
        effective_rank=int((e>max(float(e[0])*1e-10,1e-20)).sum()),
        relative_paired_difference_rms=float(np.sqrt(np.mean(delta**2))/max(np.sqrt(np.mean(np.concatenate([hi,lo])**2)),1e-30)))
    primary['heldout']={str(g):evaluate(x[g][valid],scores[g][valid],endpoint_mask(scores[g][valid]),sessions[valid],modes[valid],direction,pooled) for g in [0,1]}
    variants.append(primary)
    sensitivity=[]
    for d in [2,4,8,16,32]:
        bd=u[:,:min(d,u.shape[1])];w=bd@(bd.T@mean)
        if np.linalg.norm(w)>1e-12:w/=np.linalg.norm(w)
        vals={}
        for g in [0,1]:
            hh,ll=paired_arrays(x[g],scores[g],valid&endpoint_mask(scores[g]));gap=(hh-ll)@w
            vals[str(g)]=float(np.where(gap>1e-12,1.,np.where(gap< -1e-12,0.,.5)).mean()) if len(gap) else None
        sensitivity.append(dict(requested_k=d,actual_k=bd.shape[1],energy=float(e[:bd.shape[1]].sum()/max(e.sum(),1e-30)),heldout_ordering=vals))
    # Continuous quality is evaluated on ALL original pairs, including middle and same-class outcomes.
    source_delta=x[0][:,1]-x[0][:,0];target=q[:,1]-q[:,0]
    z=source_delta@b;zmean=z[train].mean(0);zstd=z[train].std(0);zstd[zstd<1e-10]=1
    zz=(z-zmean)/zstd;ymean=target[train].mean()
    ridge=np.linalg.solve(zz[train].T@zz[train]+.01*train.sum()*np.eye(k),zz[train].T@(target[train]-ymean))
    continuous={}
    for g in [0,1]:
        zzg=((x[g][:,1]-x[g][:,0])@b-zmean)/zstd
        actual=scores[g][:,1]-scores[g][:,0];prediction=zzg@ridge+ymean
        err=prediction[valid]-actual[valid];baseline=ymean-actual[valid]
        rho=float(spearmanr(prediction[valid],actual[valid]).statistic) if np.std(prediction[valid])>1e-12 and np.std(actual[valid])>1e-12 else None
        continuous[str(g)]=dict(n=int(valid.sum()),spearman=rho,mae_pdms_100=float(np.mean(np.abs(err))*100),
            constant_mae_pdms_100=float(np.mean(np.abs(baseline))*100),
            mse_ratio_to_constant=float(np.mean(err**2)/max(np.mean(baseline**2),1e-30)))
        arrays[f'continuous_prediction_P{g}']=prediction.astype(np.float32)
        arrays[f'difference_coordinates_P{g}']=((x[g]-pooled)@b).astype(np.float32)
        arrays[f'difference_scores_P{g}']=((x[g]-pooled)@direction).astype(np.float32)
    # Route-two paired class residuals, then route-one class residuals across all final high/fail outputs.
    for cohort in ['paired','global']:
        if cohort=='paired':high,low=hi,lo
        else:
            xt=x[0][train].reshape(-1,x[0].shape[-1]);qt=q[train].reshape(-1)
            high=xt[qt>.9];low=xt[qt<.7]
        common_center=np.concatenate([high,low]).mean(0)
        for centering in ['uncentered','pooled_centered']:
            center=np.zeros_like(common_center) if centering=='uncentered' else common_center
            ub,info=residual_basis(high,low,center)
            w=ub@(ub.T@(high.mean(0)-low.mean(0)))
            if np.linalg.norm(w)>1e-12:w/=np.linalg.norm(w)
            name=f'{cohort}_class_residual_{centering}'
            variants.append(dict(name=name,**info,heldout={str(g):evaluate(x[g][valid],scores[g][valid],endpoint_mask(scores[g][valid]),sessions[valid],modes[valid],w,center) for g in [0,1]}))
            arrays[f'{name}_basis']=ub;arrays[f'{name}_center']=center;arrays[f'{name}_direction']=w
            for g in [0,1]:arrays[f'{name}_coordinates_P{g}']=((x[g]-center)@ub[:,:2]).astype(np.float32)
    # Full-dimensional descriptive summaries follow low-dimensional fitting and validation.
    full={}
    for g in [0,1]:
        xx=x[g][valid];difference=xx[:,1]-xx[:,0]
        full[str(g)]=dict(relative_source_difference_rms=float(np.sqrt(np.mean(difference**2))/max(np.sqrt(np.mean(xx**2)),1e-30)),
            source_cosine_mean=float(np.mean(np.sum(xx[:,0]*xx[:,1],1)/np.maximum(np.linalg.norm(xx[:,0],axis=1)*np.linalg.norm(xx[:,1],axis=1),1e-30))))
    from paired_observation import save_arrays
    save_arrays(out/'cells'/f'{cell}.npz',**arrays)
    result=dict(**base,status='COMPLETE',variants=variants,dimension_sensitivity=sensitivity,continuous_quality=continuous,
                full_dimension=full,numeric_floor_flag=primary['relative_paired_difference_rms']<1e-6)
    atomic(out/'cells'/f'{cell}.json',result)
    return {k:v for k,v in result.items() if k!='variants'}


def fdr(rows,key):
    p=np.asarray([r['p'] if r['p'] is not None else 1. for r in rows]);order=np.argsort(p);m=len(p)
    adjusted=np.minimum.accumulate((p[order]*m/np.arange(1,m+1))[::-1])[::-1].clip(0,1)
    for i,v in zip(order,adjusted):rows[i][key]=float(v)


def run(args):
    out=ROOT/'analysis'/args.output;out.mkdir(parents=True,exist_ok=True)
    assert not (out/'COMPLETE.json').exists()
    acceptance=read(ROOT/'runs'/args.run/'formal_acceptance/ACCEPTANCE.json');assert acceptance['status']=='PASS'
    if not (out/'cache/COMPLETE.json').exists():make_cache(args.run,out)
    metadata=read(out/'cache/metadata.json')
    jobs=[(str(out),layer,token) for layer in range(19) for token in range(8)]
    pending=[j for j in jobs if not (out/'cells'/f'layer{j[1]:02d}_token{j[2]}.json').exists()]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn')) as pool:
        for i,r in enumerate(pool.map(fit_cell,pending),1):
            atomic(out/'STATUS.json',dict(status='LOW_DIMENSION',completed=i,total=len(pending),time=stamp()))
            if i%8==0:print(json.dumps(dict(stage='low_dimension',completed=i,total=len(pending))),flush=True)
    cells=[read(out/'cells'/f'layer{l:02d}_token{t}.json') for l in range(19) for t in range(8)]
    primary=[];secondary=[]
    for c in cells:
        if c['status']!='COMPLETE':continue
        for v in c['variants']:
            for g,test in v['heldout'].items():
                r=dict(cell=c['cell'],layer=c['layer'],token=c['token'],variant=v['name'],noise_group=int(g),**test)
                (primary if v['name']=='paired_difference_svd' else secondary).append(r)
    fdr(primary,'q_fdr');fdr(secondary,'q_fdr_secondary')
    atomic(out/'primary_tests.json',primary);atomic(out/'secondary_tests.json',secondary)
    valid_cells=[c for c in cells if c['status']=='COMPLETE']
    featured=max(valid_cells,key=lambda c:c['variants'][0]['top8_energy'])['cell'] if valid_cells else None
    result=dict(status='COMPLETE',time=stamp(),source_run=args.run,scenes=len(metadata),cells=len(cells),
        primary_family=len(primary),secondary_family=len(secondary),featured_cell=featured,
        primary_significant_positive=sum(r['q_fdr']<.05 and r['ordering']>.5 for r in primary if r['ordering'] is not None),
        fit_subset='exploration',fit_noise_group=0,validation_bases_fixed=True,validation_noise_groups=[0,1],
        uncertainty='session bootstrap500, cluster sign permutation1999, BH FDR',
        original_gt_quality_gate=False,repair_performed=False,test_cache_access=False,
        primary_config_sha256=sha(ROOT/'configs/observation_analysis_v1.json'))
    atomic(out/'COMPLETE.json',result);atomic(out/'STATUS.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--output',required=True)
    p.add_argument('--workers',type=int,default=4);args=p.parse_args();setup(f'analysis/{args.output}');compatibility();run(args)
