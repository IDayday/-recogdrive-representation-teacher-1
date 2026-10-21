"""Independent direct-data eigenspaces + direct residual SVD against saved confirmation fits."""
from common import *
import numpy as np
from scipy.linalg import eigh,svd
from threadpoolctl import threadpool_limits
from subspace_scan_prepare import OUT


def direct_basis(a,center):
    z=a-center;e,u=eigh(z.T@z/len(z),check_finite=False);e=e[::-1];u=u[:,::-1];rank=int((e>max(e[0]*1e-10,1e-20)).sum());return u[:,:rank]


def main():
    setup('subspace_scan/golden');doc=read(OUT/'CONFIRMATION_RESULTS.json');regions=doc['regions'];checked=[]
    with threadpool_limits(limits=4):
        for route in ['r1','r2']:
            for centering in ['uncentered','pooled_centered']:
                pool=[r for r in regions if r['route']==route and r['centering']==centering and r['leader'].get('P0') and not r['leader']['rank']['cutoff_degenerate']]
                if not pool:checked.append(dict(route=route,centering=centering,status='NO_UNIQUE_CUTOFF_EXAMPLE'));continue
                region=max(pool,key=lambda r:r['leader']['P0']['auc']);leader=region['leader'];config=leader['config'];cell=leader['cell'];path=OUT/'cache'/(cell+'.npy')
                x=np.load(path,mmap_mode='r');meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'));train=np.array([r['subset']=='exploration' for r in meta])
                if route=='r1':
                    q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');hi=np.array(x[train&(q>.9)],dtype=np.float64);lo=np.array(x[train&(q<.7)],dtype=np.float64)
                else:
                    from subspace_scan_cv import endpoint
                    q=np.load(OUT/f'cache/r2_a{leader["task"]["start"]}_scores.npy');mask=train&endpoint(q[0]);a=np.array(x[0,mask],dtype=np.float64);s=q[0,mask];ii=np.arange(len(a));hi=a[ii,np.argmax(s,axis=1)];lo=a[ii,np.argmin(s,axis=1)]
                mh=hi.mean(0);ml=lo.mean(0);center=(hi.sum(0)+lo.sum(0))/(len(hi)+len(lo)) if centering=='pooled_centered' else np.zeros(x.shape[-1])
                us=direct_basis(hi,center)[:,:config['ks']];uf=direct_basis(lo,center)[:,:config['kf']]
                residual=uf-us@(us.T@uf);b,s,_=svd(residual,full_matrices=False,check_finite=False,lapack_driver='gesvd');b=b[:,:config['r']]
                w=b@(b.T@(ml-mh));w/=np.sqrt((np.var(hi@w)+np.var(lo@w))*.5)
                fit=ROOT/leader['fit']['path'];assert sha(fit)==leader['fit']['sha256']
                with np.load(fit,allow_pickle=False) as z:
                    column=z['indices'].tolist().index(leader['index']);saved=z['weights'][:,column];mid=z['midpoint']
                relative=float(np.linalg.norm(w-saved)/max(np.linalg.norm(w),1e-30));cos=float(w@saved/np.linalg.norm(w)/np.linalg.norm(saved));mid_diff=float(np.max(np.abs(mid-(mh+ml)*.5)))
                assert relative<1e-5 and cos>1-1e-7 and mid_diff<1e-7,(cell,relative,cos,mid_diff)
                checked.append(dict(status='PASS',route=route,cell=cell,centering=centering,config=config,relative_weight_difference=relative,direction_cosine=cos,midpoint_max_difference=mid_diff,fit_sha256=sha(fit)))
    assert any(r['status']=='PASS' for r in checked)
    atomic(OUT/'DIRECT_SVD_INDEPENDENT_AUDIT.json',dict(status='PASS',time=stamp(),checks=checked,code_sha256=sha(Path(__file__)),
        independent_path='recompute directly centered class Gram from raw cache, direct residual gesvd; no reused full moments/Gram-SVD residual helper'))
    print(json.dumps(dict(status='PASS',examples=sum(r['status']=='PASS' for r in checked))),flush=True)

if __name__=='__main__':main()
