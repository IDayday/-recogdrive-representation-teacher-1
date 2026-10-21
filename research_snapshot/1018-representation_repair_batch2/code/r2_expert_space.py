"""Subgroup-specific spaces/operators; shared success statistics, independent failure SVD."""
from r2_common import *
from functools import lru_cache


def save_npz(path,**arrays):
    import numpy as np
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('wb') as stream: np.savez(stream,**arrays)
    tmp.replace(path)
    return sha(path)


@lru_cache(maxsize=1)
def metadata():
    import numpy as np
    s=read(ROOT/'manifests/data_source.json');rows=read(s['rows']);q=np.load(s['quality'])
    exp=np.array([r['subset']=='exploration' for r in rows])
    fold=np.array([int(digest({'session':r['session'],'cv_root':20261016})[:8],16)%5 for r in rows])
    return rows,q,exp,fold


def symmetric_eigen(a):
    import numpy as np
    from scipy.linalg import eigh
    values,vectors=eigh((a+a.T)*.5,check_finite=False)
    values=np.maximum(values[::-1],0);vectors=vectors[:,::-1]
    rank=int(np.count_nonzero(values>max(float(values[0])*1e-10,1e-20)))
    return vectors[:,:rank],values[:rank],rank


def success_geometry(cell,held):
    import numpy as np
    folder=ROOT/'analysis/success_geometry'/cell['cell']/f'fold{held}'
    ready=folder/'COMPLETE.json'
    if ready.exists(): return read(ready)
    lock=folder.with_name(folder.name+'.claim');lock.parent.mkdir(parents=True,exist_ok=True)
    try: lock.mkdir()
    except FileExistsError:
        began=time.monotonic()
        while not ready.exists():
            if time.monotonic()-began>900:raise TimeoutError('Success geometry lock stalled: '+str(folder))
            time.sleep(2)
        return read(ready)
    rows,q,exp,fold=metadata();x=np.load(cell['absolute_path'],mmap_mode='r')
    train=exp&((fold!=held) if held>=0 else True)&np.isfinite(x[:,0])
    si=np.flatnonzero(train&(q>.9));fi=np.flatnonzero(train&(q<.7))
    assert len(si)>1 and len(fi)>1
    moment=OLD/('vlm_semantic_v2' if cell['group'].endswith('_v2') else 'vlm_repair_v1')/'moments'/(cell['cell']+'.npz')
    if held<0 and moment.exists():
        with np.load(moment) as z:
            assert int(z['ns'])==len(si) and int(z['nf'])==len(fi)
            ss=np.array(z['ss']);gs=np.array(z['gs']);sf=np.array(z['sf'])
    else:
        a=np.asarray(x[si],dtype=np.float64);ss=a.sum(0);gs=a.T@a
        sf=np.asarray(x[fi],dtype=np.float64).sum(0)
    ms=ss/len(si);center=(ss+sf)/(len(si)+len(fi));cov=gs/len(si)-np.outer(ms,ms)
    output=dict(ms=ms,common_center=center,covariance=cov)
    ranks={}
    for centered in [False,True]:
        c=center if centered else np.zeros(len(ms))
        u,e,r=symmetric_eigen(gs/len(si)-np.outer(ms,c)-np.outer(c,ms)+np.outer(c,c))
        key='centered' if centered else 'uncentered';output[key+'_basis']=u;output[key+'_eigenvalues']=e;ranks[key]=r
    ordered=sorted(si,key=lambda i:digest({'token':rows[i]['token'],'expert_success_prototype':20261018}))[:512]
    output['prototype_values']=np.asarray(x[ordered],dtype=np.float32)
    output['prototype_indices']=np.asarray(ordered,dtype=np.int64)
    output['quality_mean']=np.asarray(q[si].mean())
    output['quality_covariance']=np.asarray(x[si],dtype=np.float64).T@(q[si]-q[si].mean())/len(si)
    target=folder/'geometry.npz';hashed=save_npz(target,**output)
    result=dict(status='PASS',time=stamp(),cell=cell['cell'],heldout_fold=held,path=str(target.relative_to(ROOT)),
                sha256=hashed,ranks=ranks,success_cases=len(si),global_failure_cases=len(fi),
                common_center='pooled success plus all training failures; shared across experts',
                test_accessed=False,validation_fitted=False)
    atomic(ready,result);return result


def regular(c):
    import numpy as np
    return .9*c+.1*max(float(np.trace(c)/len(c)),1e-8)*np.eye(len(c))


def matrix_sqrt(c,inverse=False):
    import numpy as np
    from scipy.linalg import eigh
    v,u=eigh((c+c.T)*.5,check_finite=False)
    return (u*np.maximum(v,1e-10)**(-.5 if inverse else .5))@u.T


def weighted_auc(high,failed,weights):
    import numpy as np
    a=np.sort(high);l=np.searchsorted(a,failed,side='left');r=np.searchsorted(a,failed,side='right')
    return float(weights@((l+r)*.5)/(len(a)*weights.sum()))


def run(task):
    import numpy as np
    from scipy.linalg import svd
    cell=task['cell'];held=task.get('heldout_fold',-1);expert=task['expert']
    rows,q,exp,fold=metadata();x=np.load(cell['absolute_path'],mmap_mode='r')
    group=read(ROOT/task['responsibility_meta'])
    with np.load(ROOT/group['path']) as z:
        indices=np.array(z['global_indices']);weights=np.array(z['responsibility'][:,expert],dtype=np.float64)
    use=np.isfinite(x[indices,0])&(weights>0)
    indices=indices[use];weights=weights[use]
    assert np.all(exp[indices]) and (held<0 or np.all(fold[indices]!=held))
    ess=float(weights.sum()**2/(weights@weights))
    sessions=len({rows[i]['session'] for i in indices[weights>weights.max()*.25]})
    destination=ROOT/'analysis/expert_spaces'/task['id']
    if ess<24 or sessions<4:
        result=dict(status='INELIGIBLE',time=stamp(),effective_cases=ess,sessions=sessions,task=task)
        atomic(destination.with_suffix('.json'),result);return result
    geometry=success_geometry(cell,held)
    with np.load(ROOT/geometry['path']) as z: data={key:np.array(z[key]) for key in z.files}
    failed=np.asarray(x[indices],dtype=np.float64);mf=weights@failed/weights.sum();ms=data['ms'];gap=mf-ms
    centered=bool(task.get('centered',True));key='centered' if centered else 'uncentered'
    center=data['common_center'] if centered else np.zeros(len(mf));us=data[key+'_basis']
    weighted=(failed-center)*np.sqrt(weights/weights.sum())[:,None]
    _,singular,vt=svd(weighted,full_matrices=False,check_finite=False,lapack_driver='gesdd')
    actual_rank=int(np.count_nonzero(singular>max(float(singular[0])*1e-5,1e-10)))
    uf=vt[:actual_rank].T;ef=singular[:actual_rank]**2
    candidates=[]
    def add(kind,b,ks=None,kf=None):
        if b is None or not b.shape[1]:return
        for r in [2,4,8,16,24,32,48,64,96,128,192,256,384,512,768,1024]:
            if r<=b.shape[1]:candidates.append(dict(kind=kind,r=r,ks=ks,kf=kf,basis=b[:,:r]))
    add('success_pca',us);add('failure_pca',uf)
    # Broad main-space endpoints are represented; infeasible subgroup ranks are
    # explicitly excluded. Neighbour grids are expanded after actual responses.
    main=[4,8,16,24,32,48,64,96,128,192,256,384,512,768,1024,1536,2048,3072,4096]
    pairs={(k,k) for k in main}
    pairs.update([(8,64),(64,8),(16,128),(128,16),(32,256),(256,32)])
    for ks,kf in sorted(pairs):
        if ks>=x.shape[1] or ks>us.shape[1] or kf>uf.shape[1]:continue
        a=us[:,:ks];b=uf[:,:kf];res=b-a@(a.T@b)
        for variance in [False,True]:
            v=res*np.sqrt(ef[:kf])[None,:] if variance else res
            u,e,rank=symmetric_eigen(v.T@v)
            valid=e>max(float(e[0])*1e-10,1e-12) if len(e) else np.zeros(0,dtype=bool)
            if not valid.any():continue
            basis=v@u[:,valid]/np.sqrt(e[valid])[None,:]
            add('variance_residual' if variance else 'basis_residual',basis,ks,kf)
    if not candidates:
        result=dict(status='INELIGIBLE',time=stamp(),reason='No eligible rank>=4 subgroup space',
                    actual_failure_rank=actual_rank,ess=ess,task=task)
        atomic(destination.with_suffix('.json'),result);return result
    prototype=(data['prototype_values']-center)
    high_order=data['prototype_indices']
    # Evaluate all candidate probes together. These are training descriptors,
    # never claimed as cross-session confirmation or intervention gains.
    vectors=np.column_stack([c['basis']@(c['basis'].T@gap) for c in candidates])
    hs=(np.asarray(x[high_order],dtype=np.float64)-center)@vectors
    fs=(failed-center)@vectors
    for j,c in enumerate(candidates):c['training_auc']=weighted_auc(hs[:,j],fs[:,j],weights)
    retained=[]
    for kind in ['success_pca','failure_pca','basis_residual','variance_residual']:
        for lo,hi in [(2,32),(33,1024)]:
            choices=[c for c in candidates if c['kind']==kind and lo<=c['r']<=hi]
            choices.sort(key=lambda c:(c['training_auc'],-c['r']),reverse=True)
            if choices:retained.append(choices[0])
    fits=[]
    for cfg in retained:
        b=cfg['basis'];r=b.shape[1];zs=(ms-center)@b;zf=(mf-center)@b
        cs=regular(b.T@data['covariance']@b)
        projected=(failed-mf)@b;cf=regular((projected*weights[:,None]).T@projected/weights.sum())
        sh=matrix_sqrt(cs);transport=sh@matrix_sqrt(sh@cf@sh,inverse=True)@sh
        qf=float(weights@q[indices]/weights.sum())
        cross_f=failed.T@(weights*(q[indices]-qf))/weights.sum()
        cross=.5*(data['quality_covariance']+cross_f)+.25*(ms-mf)*(float(data['quality_mean'])-qf)
        direction=np.linalg.solve(regular((cs+cf)*.5),b.T@cross)
        direction=direction/max(np.linalg.norm(direction),1e-12)*max(np.linalg.norm(zs-zf),1e-4)
        spec={k:v for k,v in cfg.items() if k!='basis'}
        ident=digest(dict(task=task['id'],config=spec))[:24]
        rng=np.random.default_rng(int(ident[:16],16));haar=np.linalg.qr(rng.standard_normal(b.shape),mode='reduced')[0]
        arrays=dict(basis=b,center=center,mh=zs,mf=zf,transport=transport,scale=np.sqrt(np.diag(cs)),
                    quality_direction=direction,prototypes=prototype@b,haar=haar,
                    cov_inv_s=np.linalg.inv(cs),cov_inv_f=np.linalg.inv(cf),
                    risk_center=ms,risk_direction=gap/max(np.linalg.norm(gap),1e-12))
        path=ROOT/'fits'/ident[0:2]/(ident+'.npz')
        hashed=save_npz(path,**{key:value.astype('float32') for key,value in arrays.items()})
        meta=dict(status='PASS',time=stamp(),id=ident,path=str(path.relative_to(ROOT)),sha256=hashed,
                  block=cell['block'],group=cell['group'],cell=cell['cell'],config=spec,r=r,
                  system=group['id'],expert=expert,K=group['K'],fit_seed=group['fit_seed'],
                  responsibility_path=group['path'],responsibility_sha256=group['sha256'],
                  source_sha256=cell['sha256'],heldout_fold=held,centered=centered,
                  effective_failure_cases=ess,failure_numeric_rank=actual_rank,sessions=sessions,
                  success_cases=geometry['success_cases'],reference='shared_success_bank',
                  bases_refitted_for_subgroup=True,training_descriptor_only=True)
        atomic(path.with_suffix('.json'),meta);fits.append(meta)
    result=dict(status='PASS',time=stamp(),task=task,actual_failure_rank=actual_rank,ess=ess,
                scanned_spaces=len(candidates),space_search_main_pairs=[list(p) for p in sorted(pairs)],
                fits=fits,success_geometry=geometry)
    atomic(destination.with_suffix('.json'),result)
    return dict(path=str(destination.with_suffix('.json').relative_to(ROOT)),fits=len(fits),scanned_spaces=len(candidates))
