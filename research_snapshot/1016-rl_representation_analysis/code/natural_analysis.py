"""True route-one analysis of the full natural S0 population, separate from GT pairs."""
from common import *
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import io
import multiprocessing as mp
import numpy as np

OUT=None
MAPS={}
PRIMARY_K=8


def init(out):
    global OUT,MAPS
    OUT=Path(out);MAPS={}


def field(group,name):
    key=(group,name)
    if key not in MAPS:MAPS[key]=np.load(OUT/'moments'/group/f'{name}.npy',mmap_mode='r')
    return MAPS[key]


def slice_field(group,source,name,step,layer,token):
    a=field(group,f'{source}_{name}')
    return np.asarray(a[step,layer,token] if source=='representations' else a[step,token],dtype=np.float64)


def moment(group,source,step,layer,token):
    n=int(field(group,'n'));mu=slice_field(group,source,'sum',step,layer,token)/n
    second=slice_field(group,source,'gram',step,layer,token)/n
    xy=slice_field(group,source,'xy',step,layer,token)/n
    return dict(n=n,mean=mu,second=second,xy=xy,y=float(field(group,'sum_y'))/n,y2=float(field(group,'sum_y2'))/n)


def combine(values):
    n=sum(v['n'] for v in values)
    return dict(n=n,**{k:sum(v[k]*v['n'] for v in values)/n for k in ['mean','second','xy','y','y2']})


def eig_basis(second,mean,center):
    from scipy.linalg import eigh
    c=second-np.outer(mean,center)-np.outer(center,mean)+np.outer(center,center)
    c=(c+c.T)/2
    eigen,u=eigh(c,check_finite=False);order=np.argsort(eigen)[::-1]
    eigen=np.maximum(eigen[order],0);u=u[:,order]
    rank=int((eigen>max(float(eigen[0])*1e-10,1e-20)).sum())
    return u[:,:min(rank,32)],eigen


def residual(us,uf,k):
    k=min(k,us.shape[1],uf.shape[1]);a=us[:,:k];b=uf[:,:k]
    if k==0:return np.zeros((us.shape[0],0)),[],0.
    r=b-a@(a.T@b);v,s,_=np.linalg.svd(r,full_matrices=False)
    return v[:,s>1e-6],s,float(np.linalg.norm(a.T@b,'fro')**2/k)


def project_moment(m,b,center):
    mu=(m['mean']-center)@b
    covariance=b.T@(m['second']-np.outer(m['mean'],m['mean']))@b
    covariance=(covariance+covariance.T)/2
    if m['n']>1:covariance*=m['n']/(m['n']-1)
    return dict(n=m['n'],mean=mu.tolist(),covariance=covariance.tolist())


def fit_cell(job):
    step,layer,token=job;source='representations' if layer<18 else 'dit_output';d=384 if layer<18 else 512
    s=moment('exploration__high_quality',source,step,layer,token)
    f=moment('exploration__failure',source,step,layer,token)
    middle=moment('exploration__intermediate',source,step,layer,token)
    all_train=combine([s,f,middle]);pooled=combine([s,f])['mean'];gap=f['mean']-s['mean']
    arrays={};variants=[]
    for centering in ['uncentered','pooled_centered']:
        center=np.zeros(d) if centering=='uncentered' else pooled
        us,es=eig_basis(s['second'],s['mean'],center);uf,ef=eig_basis(f['second'],f['mean'],center)
        b,singular,overlap=residual(us,uf,8);rank=b.shape[1]
        padded=np.zeros((d,8));padded[:,:rank]=b
        direction=b@(b.T@gap)
        if np.linalg.norm(direction)>1e-12:direction/=np.linalg.norm(direction)
        weights=padded.T@direction
        variance=padded.T@(all_train['second']-np.outer(all_train['mean'],all_train['mean']))@padded
        scale=np.sqrt(np.maximum(np.diag(variance),0));scale[scale<1e-10]=1
        cross=padded.T@(all_train['xy']-all_train['mean']*all_train['y'])/scale
        ridge=np.linalg.solve(variance/scale[:,None]/scale[None,:]+.01*np.eye(8),cross)
        arrays.update({f'{centering}_success_basis':us,f'{centering}_failure_basis':uf,
            f'{centering}_success_spectrum':es,f'{centering}_failure_spectrum':ef,
            f'{centering}_residual_basis':padded,f'{centering}_center':center,
            f'{centering}_direction':direction,f'{centering}_direction_coords':weights,
            f'{centering}_ridge_weights':ridge,f'{centering}_ridge_scale':scale,
            f'{centering}_ridge_mean_raw':all_train['mean']@padded})
        distributions={}
        for subset in ['exploration','validation']:
            distributions[subset]={label:project_moment(moment(f'{subset}__{label}',source,step,layer,token),padded,center)
                                   for label in ['high_quality','failure','intermediate']}
        comparisons={}
        for subset,values in distributions.items():
            ms=np.asarray(values['high_quality']['mean']);mf=np.asarray(values['failure']['mean'])
            cs=np.asarray(values['high_quality']['covariance']);cf=np.asarray(values['failure']['covariance'])
            comparisons[subset]=dict(mean_gap_l2=float(np.linalg.norm(mf-ms)),covariance_gap_frobenius=float(np.linalg.norm(cf-cs,'fro')),
                relative_covariance_gap=float(np.linalg.norm(cf-cs,'fro')/max(np.sqrt(np.linalg.norm(cf,'fro')**2+np.linalg.norm(cs,'fro')**2),1e-30)))
        sensitivity=[]
        for k in [2,4,8,16,32]:
            bk,sk,ok=residual(us,uf,k)
            sp=project_moment(s,bk,center);fp=project_moment(f,bk,center)
            cm=(np.asarray(sp['covariance'])+np.asarray(fp['covariance']))/2
            dg=np.asarray(fp['mean'])-np.asarray(sp['mean'])
            standardized=float(dg@np.linalg.pinv(cm+max(np.trace(cm)/max(len(cm),1),1e-12)*1e-6*np.eye(len(cm)))@dg) if len(cm) else 0.
            sensitivity.append(dict(requested_k=k,actual_k=min(k,us.shape[1],uf.shape[1]),residual_rank=bk.shape[1],
                residual_singular_values=np.asarray(sk).tolist(),residual_energy=float(np.sum(np.asarray(sk)**2)),
                subspace_overlap=ok,exploration_standardized_mean_gap_squared=standardized,
                success_energy=float(es[:k].sum()/max(es.sum(),1e-30)),failure_energy=float(ef[:k].sum()/max(ef.sum(),1e-30))))
        variants.append(dict(centering=centering,k=min(8,us.shape[1],uf.shape[1]),residual_rank=rank,
            residual_singular_values=np.asarray(singular).tolist(),residual_energy=float(np.sum(np.asarray(singular)**2)),
            subspace_overlap=overlap,distributions=distributions,distribution_comparisons=comparisons,sensitivity=sensitivity,
            ridge_y_mean=all_train['y'],ridge_y_variance=all_train['y2']-all_train['y']**2))
    from natural_representation import write_npz
    cell=f'step{step}_layer{layer:02d}_token{token}'
    path=OUT/'cells'/f'{cell}.npz';hashed=write_npz(path,**arrays)
    covariance_s=s['second']-np.outer(s['mean'],s['mean']);covariance_f=f['second']-np.outer(f['mean'],f['mean'])
    full=dict(quality_mean_gap_l2=float(np.linalg.norm(gap)),relative_quality_mean_gap=float(np.linalg.norm(gap)/max(np.sqrt(np.trace(s['second'])+np.trace(f['second'])),1e-30)),
        success_variance_trace=float(np.trace(covariance_s)),failure_variance_trace=float(np.trace(covariance_f)),
        quality_covariance_gap_frobenius=float(np.linalg.norm(covariance_f-covariance_s,'fro')))
    result=dict(status='COMPLETE',route='route1_natural_model_S0',cell=cell,step_index=step,step_t=[80,60,40,20,0][step],
        layer=layer,token=token,source=source,dim=d,n_success=s['n'],n_failure=f['n'],n_intermediate=middle['n'],
        variants=variants,full_dimension=full,basis_sha256=hashed,natural_source=True,gt_initialization=False)
    atomic(path.with_suffix('.json'),result);return cell


def merge(args):
    global OUT
    out=OUT;base=ROOT/'runs'/args.run
    assert (base/'COLLECTION_READY.json').exists()
    groups=[read(base/f'node{node}/moments/COMPLETE.json')['groups'] for node in range(2)]
    counts={}
    for group in sorted(set(groups[0])|set(groups[1])):
        accum={}
        for files in groups:
            src=files[group];data=retry(lambda:Path(src['path']).read_bytes())
            assert hashlib.sha256(data).hexdigest()==src['sha256']
            with np.load(io.BytesIO(data),allow_pickle=False) as z:
                for name in z.files:
                    if name not in accum:accum[name]=z[name].copy()
                    else:accum[name]+=z[name]
        folder=out/'moments'/group;folder.mkdir(parents=True,exist_ok=True)
        for name,value in accum.items():np.save(folder/f'{name}.npy',value)
        counts[group]=int(accum['n'])
        print(json.dumps(dict(stage='merge_moments',group=group,n=counts[group])),flush=True)
    metadata=read(ROOT/'manifests/natural_s0.json')
    expected=dict(Counter(f'{r["subset"]}__{r["quality"]}' for r in metadata));assert counts==expected
    atomic(out/'metadata.json',[{k:r[k] for k in ['token','global_index','session','subset','quality','baseline_pdms_100']} for r in metadata])
    atomic(out/'moments/COMPLETE.json',dict(status='COMPLETE',time=stamp(),counts=counts,total=sum(counts.values()),natural_source=True,gt_initialization=False))
    jobs=[(s,l,t) for s in range(5) for l in range(19) for t in range(8)]
    pending=[j for j in jobs if not (out/'cells'/f'step{j[0]}_layer{j[1]:02d}_token{j[2]}.json').exists()]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn'),initializer=init,initargs=(str(out),)) as pool:
        for i,cell in enumerate(pool.map(fit_cell,pending),1):
            if i%32==0:
                atomic(out/'STATUS.json',dict(status='FITTING_NATURAL_SUBSPACES',completed=i,total=len(pending),time=stamp()))
                print(json.dumps(dict(stage='fit_natural',completed=i,total=len(pending))),flush=True)
    h=np.lib.format.open_memmap(out/'bases_hidden.npy',mode='w+',dtype=np.float64,shape=(5,18,8,384,16))
    z=np.lib.format.open_memmap(out/'bases_output.npy',mode='w+',dtype=np.float64,shape=(5,8,512,16))
    for step,layer,token in jobs:
        with np.load(out/'cells'/f'step{step}_layer{layer:02d}_token{token}.npz',allow_pickle=False) as b:
            value=np.concatenate([b['uncentered_residual_basis'],b['pooled_centered_residual_basis']],axis=-1)
            if layer<18:h[step,layer,token]=value
            else:z[step,token]=value
    h.flush();z.flush()
    atomic(out/'BASES_READY.json',dict(status='COMPLETE',time=stamp(),cells=760,variants=1520,fit_subset='exploration',
        source='103288 natural S0 outputs',gt_initialization=False,counts=counts))


def project_chunk(job):
    import numpy as np
    from natural_representation import write_npz
    path,out=job;out=Path(out);doc=read(path);destination=out/'projected_chunks'/f'{path.parent.parent.name}_{path.stem}.npz'
    if destination.exists() and destination.with_suffix('.json').exists():return str(destination)
    raw=retry(lambda:Path(doc['array_path']).read_bytes());assert hashlib.sha256(raw).hexdigest()==doc['array_sha256']
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
        values={}
        for field,basis in [('representations','bases_hidden.npy'),('dit_output','bases_output.npy')]:
            x=np.moveaxis(z[field],0,-2).astype(np.float64)
            b=np.load(out/basis,mmap_mode='r')
            y=x@b
            values[field]=np.moveaxis(y,-2,0).astype(np.float32)
        assert all(np.isfinite(v).all() for v in values.values())
        tile=z['representations'][:,2,7,4,:8].astype(np.float64)
    checks={}
    for subset in ['exploration','validation']:
        for label in ['high_quality','failure','intermediate']:
            mask=np.asarray([r['subset']==subset and r['quality']==label for r in doc['records']])
            if mask.any():checks[f'{subset}__{label}']=dict(n=int(mask.sum()),sum=tile[mask].sum(0).tolist(),gram=(tile[mask].T@tile[mask]).tolist())
    values['indices']=np.asarray([r['global_index'] for r in doc['records']],dtype=np.int64)
    values['scores']=np.asarray([r['score']['score'] for r in doc['records']],dtype=np.float64)
    hashed=write_npz(destination,**values)
    atomic(destination.with_suffix('.json'),dict(status='COMPLETE',source_chunk=str(path),source_array_sha256=doc['array_sha256'],
        source_hash_verified=True,array_sha256=hashed,checks=checks,n=len(doc['records']),natural_source=True,gt_initialization=False))
    return str(destination)


def projection(args):
    out=OUT;assert (out/'BASES_READY.json').exists();base=ROOT/'runs'/args.run
    chunks=sorted((base/'formal').glob('rank*/chunks/*.json'));assert len(chunks)==3232
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn')) as pool:
        for i,p in enumerate(pool.map(project_chunk,[(str(p),str(out)) for p in chunks]),1):
            if i%64==0:
                atomic(out/'STATUS.json',dict(status='PROJECTING_NATURAL_OUTPUTS',completed=i,total=len(chunks),time=stamp()))
                print(json.dumps(dict(stage='project_natural',completed=i,total=len(chunks))),flush=True)
    h=np.lib.format.open_memmap(out/'coordinates_hidden.npy',mode='w+',dtype=np.float32,shape=(103288,5,18,8,16))
    z=np.lib.format.open_memmap(out/'coordinates_output.npy',mode='w+',dtype=np.float32,shape=(103288,5,8,16))
    score=np.zeros(103288,dtype=np.float64);seen=np.zeros(103288,dtype=bool);checks={}
    for path in sorted((out/'projected_chunks').glob('*.npz')):
        doc=read(path.with_suffix('.json'));data=retry(lambda:path.read_bytes());assert hashlib.sha256(data).hexdigest()==doc['array_sha256']
        with np.load(io.BytesIO(data),allow_pickle=False) as p:
            index=p['indices'];assert not seen[index].any();seen[index]=True
            h[index]=p['representations'];z[index]=p['dit_output'];score[index]=p['scores']
        for key,value in doc['checks'].items():
            if key not in checks:checks[key]=dict(n=0,sum=np.zeros(8),gram=np.zeros((8,8)))
            checks[key]['n']+=value['n'];checks[key]['sum']+=value['sum'];checks[key]['gram']+=value['gram']
    assert seen.all();h.flush();z.flush();np.save(out/'scores.npy',score)
    for group,check in checks.items():
        assert check['n']==int(field(group,'n'))
        assert np.allclose(check['sum'],field(group,'representations_sum')[2,7,4,:8],rtol=1e-9,atol=1e-7)
        assert np.allclose(check['gram'],field(group,'representations_gram')[2,7,4,:8,:8],rtol=1e-9,atol=1e-7)
    atomic(out/'PROJECTIONS_READY.json',dict(status='COMPLETE',time=stamp(),scenes=int(seen.sum()),chunks=len(chunks),
        all_raw_chunk_hashes_verified=True,independent_raw_tile_moments_match=True,gt_initialization=False))


def evaluate_cell(job):
    from scipy.stats import rankdata,spearmanr
    from observation_analysis import auc
    step,layer,token=job;meta=read(OUT/'metadata.json');train=np.asarray([m['subset']=='exploration' for m in meta]);valid=~train
    sessions=np.asarray([m['session'] for m in meta]);q=np.load(OUT/'scores.npy');extreme=(q<.7)|(q>.9)
    coords=np.load(OUT/('coordinates_hidden.npy' if layer<18 else 'coordinates_output.npy'),mmap_mode='r')
    x=np.asarray(coords[:,step,layer,token,:] if layer<18 else coords[:,step,token,:],dtype=np.float64)
    cell=f'step{step}_layer{layer:02d}_token{token}';fitted=read(OUT/'cells'/f'{cell}.json');results=[]
    with np.load(OUT/'cells'/f'{cell}.npz',allow_pickle=False) as basis:
        for ci,name in enumerate(['uncentered','pooled_centered']):
            z=x[:,ci*8:ci*8+8];w=basis[f'{name}_direction_coords'];s=z@w
            select=valid&extreme;labels=q[select]<.7;v=s[select]
            area=auc(v,labels)
            order=np.argsort(-v,kind='stable');ys=labels[order]
            # Tie-aware average precision using end-of-tie cumulative precision.
            ends=np.r_[np.flatnonzero(np.diff(v[order])!=0),len(v)-1];tp=np.cumsum(ys)[ends];recall=tp/max(int(ys.sum()),1)
            average_precision=float(np.sum(np.diff(np.r_[0.,recall])*tp/(ends+1)))
            bins=np.unique(np.quantile(s[train&extreme],np.linspace(0,1,33)));bins[0]=-np.inf;bins[-1]=np.inf
            if len(bins)<2:bins=np.asarray([-np.inf,np.inf])
            hs=np.histogram(v[~labels],bins=bins)[0].astype(float);hf=np.histogram(v[labels],bins=bins)[0].astype(float)
            hs/=max(hs.sum(),1);hf/=max(hf.sum(),1);overlap=float(np.minimum(hs,hf).sum())
            gap=[]
            for session in sorted(set(sessions[valid])):
                m=valid&(sessions==session)
                a=s[m&(q<.7)];b=s[m&(q>.9)]
                if len(a) and len(b):gap.append(float(a.mean()-b.mean()))
            gap=np.asarray(gap);rng=np.random.default_rng(20261016)
            boot=gap[rng.integers(len(gap),size=(500,len(gap)))].mean(1) if len(gap) else np.zeros(500)
            null=rng.choice([-1.,1.],size=(1999,len(gap)))@gap/max(len(gap),1)
            observed=float(gap.mean()) if len(gap) else 0.;p=float((1+(np.abs(null)>=abs(observed)-1e-12).sum())/2000)
            pred=((z-basis[f'{name}_ridge_mean_raw'])/basis[f'{name}_ridge_scale'])@basis[f'{name}_ridge_weights']+fitted['variants'][ci]['ridge_y_mean']
            actual=q[valid];prediction=pred[valid];err=prediction-actual;constant=fitted['variants'][ci]['ridge_y_mean']-actual
            rho=float(spearmanr(prediction,actual).statistic) if np.std(prediction)>1e-12 else None
            result=dict(cell=cell,step_index=step,step_t=[80,60,40,20,0][step],layer=layer,token=token,centering=name,
                validation_success=int((~labels).sum()),validation_failure=int(labels.sum()),failure_prevalence=float(labels.mean()),
                failure_auc=area,failure_average_precision=average_precision,shared_training_bin_overlap=overlap,
                within_session_contrast_sessions=len(gap),within_session_failure_minus_success_mean=observed,
                within_session_mean_gap_ci95=np.quantile(boot,[.025,.975]).tolist(),p=p,
                continuous_pdms_spearman=rho,continuous_pdms_mae_100=float(np.abs(err).mean()*100),
                constant_mae_100=float(np.abs(constant).mean()*100),mse_ratio_to_constant=float(np.mean(err**2)/max(np.mean(constant**2),1e-30)),
                residual_rank=fitted['variants'][ci]['residual_rank'],residual_energy=fitted['variants'][ci]['residual_energy'],
                subspace_overlap=fitted['variants'][ci]['subspace_overlap'],natural_source=True,gt_initialization=False)
            results.append(result)
    atomic(OUT/'evaluation'/f'{cell}.json',results);return results


def evaluate(args):
    out=OUT;assert (out/'PROJECTIONS_READY.json').exists();jobs=[(s,l,t) for s in range(5) for l in range(19) for t in range(8)]
    tests=[]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn'),initializer=init,initargs=(str(out),)) as pool:
        for i,result in enumerate(pool.map(evaluate_cell,jobs),1):
            tests.extend(result)
            if i%32==0:print(json.dumps(dict(stage='evaluate_natural',completed=i,total=760)),flush=True)
    from observation_analysis import fdr
    fdr(tests,'q_fdr');atomic(out/'tests.json',tests)
    result=dict(status='COMPLETE',time=stamp(),route='route1_natural_model_S0',source_run=args.run,natural_population=103288,
        success=90153,failure=2288,intermediate=10847,cells=760,primary_tests=1520,fit_subset='exploration',
        comparison='unpaired natural successes versus natural failures; not GT candidates',gt_initialization=False,
        all_five_steps=True,positive_within_session_fdr05=sum(t['q_fdr']<.05 and t['within_session_failure_minus_success_mean']>0 for t in tests),
        fixed_projection=True,independent_sessions=True,intervention=False,test_cache_access=False)
    atomic(out/'COMPLETE.json',result);atomic(out/'STATUS.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['merge_fit','project','evaluate','all']);p.add_argument('--run',required=True)
    p.add_argument('--output',default='natural_route1_v1');p.add_argument('--workers',type=int,default=6);args=p.parse_args()
    setup(f'natural_analysis/{args.output}');compatibility();out=ROOT/'analysis'/args.output;out.mkdir(parents=True,exist_ok=True);init(str(out))
    if args.command in ['merge_fit','all']:merge(args)
    if args.command in ['project','all']:projection(args)
    if args.command in ['evaluate','all']:evaluate(args)
