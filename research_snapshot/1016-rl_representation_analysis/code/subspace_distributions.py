"""Full r-dimensional distributions of the already frozen candidates, descriptive only.
These statistics never select or replace candidates; original CV/readout remains frozen.
"""
from common import *
import numpy as np
from scipy.linalg import eigh
from threadpoolctl import threadpool_limits
from subspace_scan_prepare import OUT
from subspace_scan_math import basis_moments,residual
from subspace_scan_cv import original_moments,endpoint


def mom(x):
    x=np.asarray(x,dtype=np.float64);mean=x.mean(0);return dict(n=len(x),mean=mean,cov=x.T@x/len(x)-np.outer(mean,mean))

def from_mom(x):
    n,total,gram=x;mean=total/n;return dict(n=n,mean=mean,cov=gram/n-np.outer(mean,mean))

def whiten(c):
    e,u=eigh((c+c.T)*.5,check_finite=False);floor=max(float(np.trace(c))/len(c)*1e-4,1e-12)
    return (u/np.sqrt(np.maximum(e,floor))[None,:])@u.T,floor,int((e>max(e[-1]*1e-10,1e-20)).sum())

def summary(a,b,basis,train_white):
    mu1=a['mean']@basis;mu0=b['mean']@basis;c1=basis.T@a['cov']@basis;c0=basis.T@b['cov']@basis;w,floor,rank=whiten((c1+c0)*.5)
    gap=mu0-mu1;diff=c0-c1
    return dict(n_high=a['n'],n_failure=b['n'],dimension=basis.shape[1],effective_pooled_covariance_rank=rank,ridge_floor=floor,
        within_group_standardized_mean_distance=float(np.linalg.norm(w@gap)),
        train_reference_standardized_mean_distance=float(np.linalg.norm(train_white@gap)),
        whitened_covariance_difference_per_sqrt_dimension=float(np.linalg.norm(w@diff@w,'fro')/np.sqrt(len(w))),
        train_reference_whitened_covariance_difference_per_sqrt_dimension=float(np.linalg.norm(train_white@diff@train_white,'fro')/np.sqrt(len(w))))

def main():
    setup('subspace_scan/distributions');doc=read(OUT/'CONFIRMATION_RESULTS.json');assert read(OUT/'DIRECT_SVD_INDEPENDENT_AUDIT.json')['status']=='PASS';records=doc['records'];results=[]
    with threadpool_limits(limits=8):
        for cell in sorted({r['cell'] for r in records}):
            rows=[r for r in records if r['cell']==cell];task=rows[0]['task'];route=task['route'];x=np.load(OUT/'cache'/(cell+'.npy'),mmap_mode='r');meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'));exp=np.array([r['subset']=='exploration' for r in meta]);valid=~exp
            if route=='r1':
                q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');train=[from_mom(original_moments(task,label)) for label in ['high_quality','failure']]
                groups={'validation_P0':[mom(x[valid&(q>.9)]),mom(x[valid&(q<.7)])]}
            else:
                q=np.load(OUT/f'cache/r2_a{task["start"]}_scores.npy');groups={}
                for label,g,mask in [('training_P0',0,exp&endpoint(q[0])),('validation_P0',0,valid&endpoint(q[0])),('validation_P1',1,valid&endpoint(q[1]))]:
                    if not mask.any():continue
                    a=np.array(x[g,mask],dtype=np.float64);s=q[g,mask];ii=np.arange(len(a));groups[label]=[mom(a[ii,np.argmax(s,axis=1)]),mom(a[ii,np.argmin(s,axis=1)])]
                train=groups.pop('training_P0')
            mh,ml=[r['mean'] for r in train];pooled=(train[0]['cov']+train[1]['cov'])*.5;d=len(mh);cache={}
            for centering in ['uncentered','pooled_centered']:
                selected=[r for r in rows if r['centering']==centering and (r.get('P0') or r.get('P1'))]
                if not selected:continue
                center=(train[0]['n']*mh+train[1]['n']*ml)/(train[0]['n']+train[1]['n']) if centering=='pooled_centered' else np.zeros(d)
                cache={};bases=[]
                for r in train:
                    mean=r['mean'];bases.append(basis_moments(r['cov']+np.outer(mean-center,mean-center))[0])
                rng=np.random.default_rng(int(digest(dict(cell=cell,root=20261016))[:16],16));randoms={}
                for j in [0,1,2]:
                    b,z=np.linalg.qr(rng.standard_normal((d,64)),mode='reduced');b*=np.where(np.diag(z)>=0,1.,-1.);randoms[j]=b
                for r in selected:
                    cfg=r['config'];identity=dict(cell=cell,route=route,centering=centering,index=r['index'],config=cfg)
                    if r['rank']['cutoff_degenerate']:
                        results.append(dict(**identity,status='NONUNIQUE_CUTOFF_NOT_RECONSTRUCTED'));continue
                    if cfg['kind']=='residual':
                        key=(cfg['ks'],cfg['kf'])
                        if key not in cache:cache[key]=residual(*bases,*key)[0]
                        b=cache[key][:,:cfg['r']]
                    elif cfg['kind']=='random':b=randoms[cfg['replicate']][:,:cfg['r']]
                    else:b=np.eye(d)
                    w=b@(b.T@(ml-mh));w/=np.sqrt(w@pooled@w)
                    with np.load(ROOT/r['fit']['path'],allow_pickle=False) as z:saved=z['weights'][:,z['indices'].tolist().index(r['index'])]
                    diff=float(np.linalg.norm(w-saved)/max(np.linalg.norm(saved),1e-30))
                    if diff>1e-5:results.append(dict(**identity,status='RECONSTRUCTED_BASIS_NOT_MATCHED',relative_probe_difference=diff));continue
                    cov=b.T@pooled@b;white,floor,rank=whiten(cov);stats={g:summary(*v,b,white) for g,v in dict(training=train,**groups).items()}
                    q1=b.T@w;q1/=np.linalg.norm(q1);project=np.eye(len(q1))-np.outer(q1,q1);e,u=eigh(project@cov@project,check_finite=False);q2=u[:,-1]
                    axes=np.stack([b@q1/np.sqrt(q1@cov@q1),b@q2/np.sqrt(max(q2@cov@q2,1e-12))],1)
                    directory=OUT/'distributions';directory.mkdir(exist_ok=True);path=directory/f'{cell}_{centering}_i{r["index"]:03d}.npz';assert not path.exists()
                    arrays=dict(basis=b,center=center,plot_axes=axes,plot_center=(mh+ml)*.5)
                    for g,v in dict(training=train,**groups).items():
                        for label,m in zip(['high','failure'],v):arrays[g+'_'+label+'_mean']=m['mean']@b;arrays[g+'_'+label+'_covariance']=b.T@m['cov']@b
                    with path.open('xb') as f:np.savez(f,**arrays)
                    results.append(dict(**identity,status='COMPLETE',statistics=stats,relative_probe_difference=diff,path=str(path.relative_to(ROOT)),sha256=sha(path),descriptive_only=True))
            print(json.dumps(dict(status='FROZEN_DISTRIBUTIONS',cell=cell,records=len(results))),flush=True)
    atomic(OUT/'FROZEN_DISTRIBUTIONS.json',dict(status='COMPLETE',time=stamp(),records=results,code_sha256=sha(Path(__file__)),
        selection_changed=False,scope='full r-dimensional class means/covariances at frozen candidates; no covariance-only candidate search',
        regularization='pooled covariance eigenvalue floor=max(trace/r*1e-4,1e-12); both within-group and fixed exploration reference whitening'))

if __name__=='__main__':main()
