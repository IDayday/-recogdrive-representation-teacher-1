"""Complete route TWO distributions and independent failure-mode spaces.

Every input here belongs to failed-output/GT paired continuation. The candidate-
pool control is explicitly NOT route one, whose input is natural S0 predictions.
"""
from common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import numpy as np


def covariance(z):
    return np.cov(z,rowvar=False).reshape(z.shape[1],z.shape[1]) if len(z)>1 else np.zeros((z.shape[1],z.shape[1]))


def distribution(z,q,direction,train_edges):
    from observation_analysis import auc
    hi=q>.9;lo=q<.7;s=z@direction
    a,b=z[hi],z[lo]
    ha=np.histogram(s[hi],bins=train_edges)[0].astype(float);hb=np.histogram(s[lo],bins=train_edges)[0].astype(float)
    ha/=max(ha.sum(),1);hb/=max(hb.sum(),1)
    ca,cb=covariance(a),covariance(b)
    return dict(n_high=int(hi.sum()),n_fail=int(lo.sum()),mean_high=a.mean(0).tolist() if len(a) else None,
        mean_fail=b.mean(0).tolist() if len(b) else None,covariance_high=ca.tolist(),covariance_fail=cb.tolist(),
        mean_gap_l2=float(np.linalg.norm(a.mean(0)-b.mean(0))) if len(a) and len(b) else None,
        covariance_gap_frobenius=float(np.linalg.norm(ca-cb,'fro')),
        shared_training_bin_overlap=float(np.minimum(ha,hb).sum()) if len(a) and len(b) else None,
        success_auc=auc(s[hi|lo],hi[hi|lo]))


def ridge(train_x,train_y,test_x,test_y):
    from scipy.stats import spearmanr
    mean=train_x.mean(0);scale=train_x.std(0);scale[scale<1e-10]=1
    x=(train_x-mean)/scale;ymean=train_y.mean()
    w=np.linalg.solve(x.T@x+.01*len(x)*np.eye(x.shape[1]),x.T@(train_y-ymean))
    pred=(test_x-mean)/scale@w+ymean;error=pred-test_y;constant=ymean-test_y
    rho=float(spearmanr(pred,test_y).statistic) if np.std(pred)>1e-12 and np.std(test_y)>1e-12 else None
    return dict(n=len(test_y),spearman=rho,mae_pdms_100=float(np.abs(error).mean()*100),
        constant_mae_pdms_100=float(np.abs(constant).mean()*100),mse_ratio_to_constant=float(np.mean(error**2)/max(np.mean(constant**2),1e-30)))


def residual_space(hi,lo,center):
    from observation_analysis import basis_svd
    us,es=basis_svd(hi-center);uf,ef=basis_svd(lo-center);k=min(8,us.shape[1],uf.shape[1])
    u,s,_=np.linalg.svd(uf[:,:k]-us[:,:k]@(us[:,:k].T@uf[:,:k]),full_matrices=False)
    return u[:,s>1e-6],dict(success_basis=us,failure_basis=uf,success_spectrum=es,failure_spectrum=ef,
                          residual_singular_values=s)


def work(job):
    out,layer,token=job;out=Path(out);previous=ROOT/'analysis/observation_v1';cache=previous/'cache'
    from observation_analysis import endpoint_mask,paired_arrays,basis_svd,cluster_test
    from natural_representation import write_npz
    meta=read(cache/'metadata.json');train=np.asarray([r['subset']=='exploration' for r in meta]);valid=~train
    sessions=np.asarray([r['session'] for r in meta]);q=np.load(cache/'scores.npy');x={}
    for g in [0,1]:
        if layer<18:x[g]=np.asarray(np.load(cache/f'hidden_P{g}.npy',mmap_mode='r')[:,:,layer,token,:],dtype=np.float64)
        else:x[g]=np.asarray(np.load(cache/f'output_P{g}.npy',mmap_mode='r')[:,:,token,:],dtype=np.float64)
    cell=f'layer{layer:02d}_token{token}';old=read(previous/'cells'/f'{cell}.json')
    summaries=[];saved={};spectra={}
    with np.load(previous/'cells'/f'{cell}.npz',allow_pickle=False) as z:
        for variant in old['variants']:
            name=variant['name'];paired=not name.startswith('global_')
            if name=='paired_difference_svd':
                b=z['difference_basis'][:,:8];center=z['paired_pooled_center'];w=z['difference_direction']
            else:b=z[f'{name}_basis'];center=z[f'{name}_center'];w=z[f'{name}_direction']
            coordinates={g:(x[g]-center)@b for g in [0,1]};wd=b.T@w
            fitcases=train&(endpoint_mask(q[0]) if paired else np.ones(len(train),dtype=bool))
            fitz=coordinates[0][fitcases].reshape(-1,b.shape[1]);fity=q[0][fitcases].reshape(-1)
            bins=np.unique(np.quantile(fitz@wd,np.linspace(0,1,33)))
            if len(bins)<2:bins=np.asarray([-np.inf,np.inf])
            else:bins[0]=-np.inf;bins[-1]=np.inf
            stats={}
            for group,mask in [('exploration_P0',train),('validation_P0',valid),('validation_P1',valid)]:
                g=1 if group.endswith('P1') else 0
                m=mask&(endpoint_mask(q[g]) if paired else np.ones(len(train),dtype=bool))
                zz=coordinates[g][m].reshape(-1,b.shape[1]);yy=q[g][m].reshape(-1)
                stats[group]=distribution(zz,yy,wd,bins)
            continuous={}
            for g in [0,1]:
                continuous[str(g)]=dict(
                    absolute_quality_all_candidates=ridge(coordinates[0][train].reshape(-1,b.shape[1]),q[0][train].reshape(-1),coordinates[g][valid].reshape(-1,b.shape[1]),q[g][valid].reshape(-1)),
                    within_scene_delta_quality_all_pairs=ridge(coordinates[0][train,1]-coordinates[0][train,0],q[0][train,1]-q[0][train,0],
                        coordinates[g][valid,1]-coordinates[g][valid,0],q[g][valid,1]-q[g][valid,0]))
            summaries.append(dict(variant=name,scope='matched quality pairs' if paired else 'all route2 paired-continuation candidates, NOT route1',
                distributions=stats,continuous_quality=continuous))
            saved[f'{name}_coordinates_P0']=coordinates[0].astype(np.float32);saved[f'{name}_coordinates_P1']=coordinates[1].astype(np.float32)
            if name!='paired_difference_svd':
                a=fitz[fity>.9];d=fitz[fity<.7]
                # Full original-space class spectra/bases make residual construction independently inspectable.
                original=x[0][fitcases].reshape(-1,x[0].shape[-1]);labels=q[0][fitcases].reshape(-1)
                us,es=basis_svd(original[labels>.9]-center);uf,ef=basis_svd(original[labels<.7]-center)
                spectra.update({f'{name}_success_basis':us,f'{name}_failure_basis':uf,
                                f'{name}_success_spectrum':es,f'{name}_failure_spectrum':ef})
    # Independent route-two spaces per FINAL failed-branch type, not a pooled direction merely re-tabulated.
    modes=np.load(out/'final_pair_modes.npy');mode_names=['collision','offroad','ttc','progress_only'];models={};coverage=[]
    for mode_index,mode in enumerate(mode_names):
        m=train&endpoint_mask(q[0])&(modes[0]==mode_index)
        n=int(m.sum());ng=len(set(sessions[m]));coverage.append(dict(mode=mode,train_pairs=n,train_sessions=ng,
            status='FIT' if n>=20 and ng>=8 else 'INSUFFICIENT_FINAL_QUALITY_PAIRS'))
        if n<20 or ng<8:continue
        hi,lo=paired_arrays(x[0],q[0],m);delta=hi-lo;ud,ed=basis_svd(delta);bd=ud[:,:min(8,ud.shape[1])]
        models[mode]={};cent=(hi.mean(0)+lo.mean(0))/2
        for method in ['difference_svd','paired_residual_uncentered','paired_residual_pooled_centered']:
            if method=='difference_svd':b=bd;extra=dict(difference_spectrum=ed)
            else:b,extra=residual_space(hi,lo,np.zeros_like(cent) if method.endswith('_uncentered') else cent)
            w=b@(b.T@delta.mean(0))
            if np.linalg.norm(w)>1e-12:w/=np.linalg.norm(w)
            models[mode][method]=(b,w)
            saved[f'{mode}_{method}_basis']=b;saved[f'{mode}_{method}_direction']=w
            for key,value in extra.items():saved[f'{mode}_{method}_{key}']=value
    transfer=[];spaces=[]
    for fitmode,methods in models.items():
        for method,(b,w) in methods.items():
            for g in [0,1]:
                for mode_index,testmode in enumerate(mode_names):
                    mask=valid&endpoint_mask(q[g])&(modes[g]==mode_index);hi,lo=paired_arrays(x[g],q[g],mask)
                    gap=(hi-lo)@w;order=np.where(gap>1e-12,1.,np.where(gap< -1e-12,0.,.5))
                    ng=len(set(sessions[mask]));qualified=len(gap)>=20 and ng>=8
                    test=cluster_test(order,sessions[mask]) if qualified else dict(n=len(gap),sessions=ng,
                        ordering=float(order.mean()) if len(order) else None,ci95=None,p=None)
                    transfer.append(dict(cell=cell,layer=layer,token=token,fit_mode=fitmode,test_mode=testmode,
                        method=method,noise_group=g,inference_qualified=qualified,**test))
            for other in sorted(models):
                if other<=fitmode:continue
                bb,ww=models[other][method];k=min(b.shape[1],bb.shape[1])
                cosine=np.linalg.svd(b[:,:k].T@bb[:,:k],compute_uv=False).clip(0,1)
                spaces.append(dict(mode_a=fitmode,mode_b=other,method=method,k=k,
                    mean_squared_principal_cosine=float(np.mean(cosine**2)) if k else None,
                    principal_angles_degrees=np.degrees(np.arccos(cosine)).tolist(),direction_cosine=float(w@ww)))
    write_npz(out/'cells'/f'{cell}.npz',**saved,**spectra)
    result=dict(status='COMPLETE',route='route2_failure_GT_pairs_only',cell=cell,layer=layer,token=token,
        summaries=summaries,independent_mode_fit_coverage=coverage,mode_subspace_comparisons=spaces,transfer_tests=transfer,
        original_gt_quality_gate=False,route1_data_used=False)
    atomic(out/'cells'/f'{cell}.json',result)
    return transfer


def main(args):
    from paired_acceptance import load_records
    from representation_prepare import primary_mode
    from observation_analysis import fdr
    out=ROOT/'analysis/paired_route2_completion_v2';out.mkdir(parents=True,exist_ok=True);assert not (out/'COMPLETE.json').exists()
    meta=read(ROOT/'analysis/observation_v1/cache/metadata.json');by={r['token']:i for i,r in enumerate(meta)}
    q=np.load(ROOT/'analysis/observation_v1/cache/scores.npy');rows=load_records('paired_formal_20261016T0728Z','formal')
    modes=np.full((2,len(meta)),-1,dtype=np.int8);names=['collision','offroad','ttc','progress_only']
    for r in rows:
        if r['start_t']!=0:continue
        g=r['noise_group'];i=by[r['token']];b=r['branch_index']
        if q[g,i,b]<.7 and q[g,i,1-b]>.9:modes[g,i]=names.index(primary_mode(r['score']))
    np.save(out/'final_pair_modes.npy',modes)
    jobs=[(str(out),l,t) for l in range(19) for t in range(8)];tests=[]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn')) as pool:
        for i,result in enumerate(pool.map(work,jobs),1):
            tests.extend(result)
            if i%8==0:
                atomic(out/'STATUS.json',dict(status='ROUTE2_DISTRIBUTION_AND_MODE_SPACES',completed=i,total=152,time=stamp()))
                print(json.dumps(dict(completed=i,total=152)),flush=True)
    qualified=[r for r in tests if r['inference_qualified']];fdr(qualified,'q_fdr')
    atomic(out/'mode_transfer_tests.json',tests)
    result=dict(status='COMPLETE',time=stamp(),route='route2_failure_GT_pairs_only',cells=152,
        distribution_variants=5,distribution_scope='paired difference, paired residuals and paired-candidate controls; all are route2',
        independent_failure_mode_spaces=True,mode_transfer_tests=len(tests),qualified_mode_transfer_family=len(qualified),
        fit_subset='exploration P0',validation='fixed spaces on held-out sessions P0/P1',route1_data_used=False,intervention=False)
    atomic(out/'COMPLETE.json',result);atomic(out/'STATUS.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=6);args=p.parse_args()
    setup('paired_route2_completion_v2');compatibility();main(args)
