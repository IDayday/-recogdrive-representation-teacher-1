"""Exploration-only repair fits for the ten already-confirmed expanded spaces."""
from common import *
import argparse
import numpy as np
from subspace_scan_math import basis_moments, residual
from subspace_scan_cv import endpoint
from repair_prepare import mapping, regular, sqrtm
from paired_observation import save_arrays

OUT=ROOT/'candidate_repair_v1'
SCAN=ROOT/'analysis/subspace_scan_v2'

def selected():
    confirmation=read(SCAN/'CONFIRMATION_RESULTS.json')
    result=[]
    for group in confirmation['regions']:
        if not group['stable_region_confirmed']:continue
        leader=group['leader'];task=leader['task']
        result.append(dict(id=group['region_id'],route=leader['route'],cell=leader['cell'],centering=leader['centering'],
            step=task['step'],layer=task['layer'],token=task['token'],config=leader['config'],
            original_fit=leader['fit'],original_index=leader['index'],confirmed_neighbors=group['positive_neighbors']))
    assert len(result)==10
    return result

def source(candidate):
    proof=read(SCAN/'CACHE_INDEX.json')['cells'][candidate['cell']]
    path=SCAN/'cache'/(candidate['cell']+'.npy');assert sha(path)==proof['sha256']
    x=np.load(path,mmap_mode='r')
    meta=read(SCAN/('natural_metadata.json' if candidate['route']=='r1' else 'paired_metadata.json'))
    exp=np.array([m['subset']=='exploration' for m in meta])
    if candidate['route']=='r1':
        q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy')
        hi=np.asarray(x[exp&(q>.9)],dtype=np.float64);lo=np.asarray(x[exp&(q<.7)],dtype=np.float64)
    else:
        q=np.load(SCAN/'cache/r2_a0_scores.npy')[0];use=exp&endpoint(q)
        a=np.asarray(x[0,use],dtype=np.float64);qq=q[use];ii=np.arange(len(a))
        hi=a[ii,np.argmax(qq,axis=1)];lo=a[ii,np.argmin(qq,axis=1)]
    return hi,lo,proof['sha256']

def basis(hi,lo,candidate,kind,replicate=0):
    d=hi.shape[1];cfg=candidate['config'];r=cfg['r']
    center=np.concatenate([hi,lo]).mean(0) if candidate['centering']=='pooled_centered' else np.zeros(d)
    if kind=='full':return np.eye(d),center,dict(effective_r=d)
    if kind=='random':
        rng=np.random.default_rng(int(digest(dict(candidate=candidate['id'],replicate=replicate,root=20261016))[:16],16))
        b,z=np.linalg.qr(rng.standard_normal((d,r)),mode='reduced');b*=np.where(np.diag(z)>=0,1.,-1.)
        return b,center,dict(effective_r=r,construction_seed_replicate=replicate)
    us,_,rs=basis_moments((hi-center).T@(hi-center)/len(hi));uf,_,rf=basis_moments((lo-center).T@(lo-center)/len(lo))
    ks=cfg['ks'] if kind=='candidate' else r;kf=cfg['kf'] if kind=='candidate' else r
    b,s,rank=residual(us,uf,ks,kf);assert rank>=r and rs>=ks and rf>=kf
    degenerate=bool(r<len(s) and abs(s[r-1]-s[r])<=max(s[0],1.)*1e-8)
    assert not degenerate,('Do not edit arbitrary repeated-singular-value truncations',candidate['id'],kind)
    return b[:,:r],center,dict(effective_r=r,rank_success=rs,rank_failure=rf,residual_rank=rank,cutoff_degenerate=False,ks=ks,kf=kf)

def project(x,b,center):
    return np.asarray(x,dtype=np.float64)-center if b.shape[0]==b.shape[1] and np.array_equal(b,np.eye(len(b))) else (np.asarray(x,dtype=np.float64)-center)@b

def fit(candidate,kind='candidate',replicate=0):
    import torch
    ident=candidate['id']+('' if kind=='candidate' else f'__{kind}{replicate}')
    dest=OUT/'fits'/(ident+'.npz');assert not dest.exists()
    hi,lo,source_sha=source(candidate);b,center,rank=basis(hi,lo,candidate,kind,replicate)
    assert np.allclose(b.T@b,np.eye(b.shape[1]),rtol=0,atol=1e-7)
    hz=project(hi,b,center);lz=project(lo,b,center)
    native_cell=f'r1_a-1_s{candidate["step"]}_l{candidate["layer"]}_t{candidate["token"]}'
    p=SCAN/'cache'/(native_cell+'.npy');proof=read(SCAN/'CACHE_INDEX.json')['cells'][native_cell];assert sha(p)==proof['sha256']
    raw=np.load(p,mmap_mode='r');meta=read(SCAN/'natural_metadata.json');exp=np.array([m['subset']=='exploration' for m in meta])
    q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');indices=np.flatnonzero(exp)
    native=project(raw[exp],b,center);qq=q[exp];nh=native[qq>.9];nl=native[qq<.7]
    arrays=dict(b=b,center=center,native_indices=indices,native_z=native.astype(np.float32))
    for prefix,high,low in [('p',hz,lz),('n',nh,nl)]:
        mh,ml,ch,cl,a=mapping(high,low)
        arrays.update({prefix+'_mh':mh,prefix+'_ml':ml,prefix+'_scale':np.sqrt(np.maximum(np.diag(ch),1e-6)),prefix+'_ot':a})
    # Natural-input calibration avoids using GT-source classification as a runtime gate.
    gap=nl.mean(0)-nh.mean(0);var=float(gap@((np.cov(nl,rowvar=False)+np.cov(nh,rowvar=False))*.5)@gap)
    risk=gap/max(np.sqrt(var),1e-12);origin=nh.mean(0);risk_high=(nh-origin)@risk
    arrays.update(risk=risk,risk_origin=origin,risk95=np.quantile(risk_high,.95),risk99=np.quantile(risk_high,.99),risk995=np.quantile(risk_high,.995))
    # Check the reconstructed original candidate against the frozen observation readout.
    cosine=None
    if kind=='candidate':
        fp=ROOT/candidate['original_fit']['path'];assert sha(fp)==candidate['original_fit']['sha256']
        with np.load(fp) as f:w=f['weights'][:,list(f['indices']).index(candidate['original_index'])]
        ours=b@(lz.mean(0)-hz.mean(0));cosine=float(ours@w/(np.linalg.norm(ours)*np.linalg.norm(w)))
        assert cosine>1-1e-6,(candidate['id'],cosine)
    learned=[]
    if candidate['route']=='r2' and kind=='candidate':
        for replay in [False,True]:
            z=np.concatenate([lz,hz]);target=np.concatenate([hz-lz,np.zeros_like(hz)])
            if replay:
                rng=np.random.default_rng(20261016);take=rng.choice(len(nh),size=min(len(nh),len(hz)),replace=False)
                z=np.concatenate([z,nh[take]]);target=np.concatenate([target,np.zeros_like(nh[take])])
            pre='replay' if replay else 'paired';zm=z.mean(0);zs=np.maximum(z.std(0),1e-5);xx=(z-zm)/zs
            scale=arrays['p_scale'];design=np.c_[xx,np.ones(len(xx))]
            reg=np.linalg.solve(design.T@design+.1*len(xx)*np.eye(len(design[0])),design.T@target)
            arrays.update({pre+'_zm':zm,pre+'_zs':zs,pre+'_reg':reg})
            rng_seed=int(digest(dict(candidate=candidate['id'],replay=replay,root=20261016))[:8],16)
            torch.manual_seed(rng_seed);net=torch.nn.Sequential(torch.nn.Linear(b.shape[1],64),torch.nn.Tanh(),torch.nn.Linear(64,b.shape[1]))
            torch.nn.init.zeros_(net[-1].weight);torch.nn.init.zeros_(net[-1].bias)
            opt=torch.optim.AdamW(net.parameters(),lr=.003,weight_decay=.01)
            xt=torch.tensor(xx,dtype=torch.float32);yt=torch.tensor(target/scale,dtype=torch.float32)
            initial=float((net(xt)-yt).square().mean().detach())
            best=None;best_loss=float('inf')
            for update in range(400):
                opt.zero_grad();pred=net(xt);loss=(pred-yt).square().mean()+.01*pred.square().mean();loss.backward();opt.step()
                value=float((net(xt)-yt).square().mean().detach())
                if value<best_loss:best_loss=value;best={k:v.detach().numpy().copy() for k,v in net.state_dict().items()}
            arrays.update({pre+'_mlp_'+k:v for k,v in best.items()})
            learned.append(dict(replay=replay,updates=400,seed=rng_seed,initial_mse=initial,best_training_mse=best_loss))
        arrays.update(local_low=lz,local_delta=hz-lz)
    # Large native coordinate matrices are stored separately; runtime fits stay small.
    coords=arrays.pop('native_z');coord_path=OUT/'coordinates'/(ident+'.npy');coord_path.parent.mkdir(parents=True,exist_ok=True)
    with coord_path.open('xb') as f:np.save(f,coords)
    save_arrays(dest,**arrays)
    spec=dict(id=ident,candidate=candidate,kind=kind,replicate=replicate,fit_path=str(dest.relative_to(ROOT)),fit_sha256=sha(dest),
        coordinate_path=str(coord_path.relative_to(ROOT)),coordinate_sha256=sha(coord_path),rank=rank,source_sha256=source_sha,
        native_source_sha256=proof['sha256'],natural_high=len(nh),natural_low=len(nl),source_high=len(hz),source_low=len(lz),
        learned=learned,original_readout_cosine=cosine,fit_subset='exploration only',validation_fit=False,time=stamp())
    atomic(dest.with_suffix('.json'),spec);print(json.dumps(dict(event='FIT_COMPLETE',id=ident,r=rank['effective_r'])),flush=True)
    return spec

def main():
    setup('candidate_repair/fit');compatibility()
    import torch;torch.set_num_threads(1)
    OUT.mkdir(exist_ok=True);candidates=selected();atomic(OUT/'CANDIDATES.json',dict(time=stamp(),candidates=candidates,source_sha256=sha(SCAN/'CONFIRMATION_RESULTS.json')))
    fits=[]
    for candidate in candidates:
        fits.append(fit(candidate))
        # Same-r minimum equal-main and full-D controls for the two main representatives.
        if candidate['id'] in ['r1_pooled_centered_unequal_region0','r2_pooled_centered_unequal_region9']:
            for kind in ['equal','full']:fits.append(fit(candidate,kind))
            for rep in [0,1,2]:fits.append(fit(candidate,'random',rep))
    atomic(OUT/'FITS_READY.json',dict(status='PASS',time=stamp(),fits=fits,candidates=10,base_parameters_updated=False))

if __name__=='__main__':main()
