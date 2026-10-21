"""Train-only repair fits and frozen experimental manifests; observation assets stay immutable."""
from common import *
import argparse
import csv
import numpy as np
from paired_observation import save_arrays

REPAIR=ROOT/'repair_v1'
NAT=ROOT/'analysis/natural_route1_v1'
PAIR=ROOT/'analysis/observation_v1'
LAYERS=[6,10,17]

def regular(c):
    c=(c+c.T)/2
    return .95*c+.05*np.eye(len(c))*max(np.trace(c)/len(c),1e-6)

def sqrtm(c,power):
    e,u=np.linalg.eigh((c+c.T)/2);return (u*np.maximum(e,1e-8)**power)@u.T

def mapping(high,low):
    mh=high.mean(0);ml=low.mean(0)
    ch=np.cov(high,rowvar=False);cl=np.cov(low,rowvar=False)
    clh=sqrtm(regular(cl),.5);cli=sqrtm(regular(cl),-.5)
    a=cli@sqrtm(clh@regular(ch)@clh,.5)@cli
    return mh,ml,ch,cl,a

def fit_site(layer,step=4,k=8):
    """Natural moments or paired P0 only. No validation observations fit a parameter."""
    import torch
    from observation_analysis import basis_svd,residual_basis,paired_arrays,endpoint_mask
    meta=read(PAIR/'cache/metadata.json');tr=np.array([r['subset']=='exploration' for r in meta])
    q=np.load(PAIR/'cache/scores.npy')[0]
    px=np.load(PAIR/'cache/hidden_P0.npy',mmap_mode='r')[:,:,layer]
    arrays={};information=[]
    for tok in range(8):
        cell=read(NAT/'cells'/f'step{step}_layer{layer:02d}_token{tok}.json')
        with np.load(NAT/'cells'/f'step{step}_layer{layer:02d}_token{tok}.npz') as d:
            if k==8:b=d['pooled_centered_residual_basis'].copy()
            else:
                us=d['pooled_centered_success_basis'][:,:k];uf=d['pooled_centered_failure_basis'][:,:k]
                u,s,_=np.linalg.svd(uf-us@(us.T@uf),full_matrices=False);b=u[:,s>1e-6]
                b=b[:,:k]
            # Full natural cohort moments are already independently audited.
        pool=cell['variants'][1]['distributions']['exploration']
        if k==8:
            high=pool['high_quality'];low=pool['failure']
            mh=np.array(high['mean']);ml=np.array(low['mean']);ch=np.array(high['covariance']);cl=np.array(low['covariance'])
        else:
            from natural_analysis_v2 import init,moment
            init(str(NAT));hs=moment('exploration__high_quality','representations',step,layer,tok)
            fs=moment('exploration__failure','representations',step,layer,tok)
            mh=hs['mean']@b;ml=fs['mean']@b
            ch=b.T@(hs['second']-np.outer(hs['mean'],hs['mean']))@b
            cl=b.T@(fs['second']-np.outer(fs['mean'],fs['mean']))@b
        # A common center is explicitly stored; natural k8 moments above use that center.
        if k==8:
            with np.load(NAT/'cells'/f'step{step}_layer{layer:02d}_token{tok}.npz') as d:center=d['pooled_centered_center'].copy()
        else:center=np.zeros(384)
        clh=sqrtm(regular(cl),.5);cli=sqrtm(regular(cl),-.5);a=cli@sqrtm(clh@regular(ch)@clh,.5)@cli
        variance=np.maximum(np.diag(ch),1e-6);scale=np.sqrt(variance)
        direction=mh-ml;direction/=max(np.linalg.norm(direction),1e-8)
        arrays.update({f'n_{tok}_b':b,f'n_{tok}_center':center,f'n_{tok}_mh':mh,f'n_{tok}_ml':ml,
                       f'n_{tok}_a':a,f'n_{tok}_scale':scale,f'n_{tok}_direction':direction})
        # Risk gate is trained from natural moments, not GT-source classification.
        risk=np.linalg.solve(regular(ch+cl),ml-mh);rs=max(np.sqrt(risk@ch@risk),1e-8)
        arrays[f'n_{tok}_risk']=risk/rs;arrays[f'n_{tok}_risk_origin']=mh
        # Native continuous-quality ridge used as a conservative linear critic.
        if k==8:
            with np.load(NAT/'cells'/f'step{step}_layer{layer:02d}_token{tok}.npz') as d:
                arrays[f'n_{tok}_critic']=d['pooled_centered_ridge_weights']/d['pooled_centered_ridge_scale']
        if step!=4:continue
        xx=np.array(px[:,:,tok],dtype=np.float64);mask=tr&endpoint_mask(q)
        hi,lo=paired_arrays(xx,q,mask);delta=hi-lo
        pb,_=basis_svd(delta,maxdim=max(k,8));pb=pb[:,:k];pc=np.concatenate([hi,lo]).mean(0)
        hz=(hi-pc)@pb;lz=(lo-pc)@pb
        ph,pl,pch,pcl,pa=mapping(hz,lz);ps=np.sqrt(np.maximum(np.diag(pch),1e-6))
        arrays.update({f'p_{tok}_b':pb,f'p_{tok}_center':pc,f'p_{tok}_mh':ph,f'p_{tok}_ml':pl,
                       f'p_{tok}_a':pa,f'p_{tok}_scale':ps,f'p_{tok}_direction':ph-pl})
        # Local conditional regression, exact paired targets plus identity at successful states.
        z=np.concatenate([lz,hz]);target=np.concatenate([hz-lz,np.zeros_like(hz)])
        zm=z.mean(0);zs=np.maximum(z.std(0),1e-5);zz=(z-zm)/zs
        design=np.c_[zz,np.ones(len(zz))]
        ridge=np.linalg.solve(design.T@design+.1*len(z)*np.eye(len(design[0])),design.T@target)
        arrays.update({f'p_{tok}_reg':ridge,f'p_{tok}_zm':zm,f'p_{tok}_zs':zs,
                       f'p_{tok}_local_low':lz,f'p_{tok}_local_delta':hz-lz})
        # Small nonlinear repair, trained entirely on exploration paired low->high and high->identity.
        torch.manual_seed(20261016+layer*100+tok)
        net=torch.nn.Sequential(torch.nn.Linear(k,32),torch.nn.Tanh(),torch.nn.Linear(32,k))
        torch.nn.init.zeros_(net[-1].weight);torch.nn.init.zeros_(net[-1].bias)
        opt=torch.optim.AdamW(net.parameters(),lr=.003,weight_decay=.01)
        xt=torch.tensor(zz,dtype=torch.float32);yt=torch.tensor(target/ps,dtype=torch.float32)
        initial=float((net(xt)-yt).square().mean().detach());loss=None
        for update in range(400):
            opt.zero_grad();pred=net(xt);loss=(pred-yt).square().mean()+.01*pred.square().mean();loss.backward();opt.step()
        final=float((net(xt)-yt).square().mean().detach())
        for name,value in net.state_dict().items():arrays[f'p_{tok}_mlp_{name}']=value.numpy()
        information.append(dict(token=tok,train_pairs=len(hi),initial_loss=initial,final_loss=final,updates=400,seed=20261016+layer*100+tok))
    out=REPAIR/'fits'/f's{step}_l{layer}_k{k}.npz';save_arrays(out,**arrays)
    atomic(out.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),fit='exploration natural moments and exploration P0 pairs only',
        layer=layer,step=step,k=k,sha256=sha(out),learned_updates=information,base_parameters_updated=False))
    return out

def prepare():
    from collections import Counter
    REPAIR.mkdir(exist_ok=True);rows=read(ROOT/'manifests/natural_s0.json')
    scores=list(csv.DictReader((ROOT/'runs/rl_s0_20261016T063037Z/delivery/scores.csv').open()))
    assert [r['token'] for r in rows]==[r['token'] for r in scores]
    # Deterministic stratified development screen; training fit and held-out validation remain distinct.
    tr=[r for r in rows if r['subset']=='exploration'];panel=[]
    for label,n in [('failure',1850),('high_quality',6000),('intermediate',2000)]:
        pool=sorted([r for r in tr if r['quality']==label],key=lambda r:digest({'token':r['token'],'repair_screen':20261016}))
        panel+=pool[:n]
    panel.sort(key=lambda r:r['global_index'])
    atomic(REPAIR/'screen.json',panel)
    atomic(REPAIR/'validation.json',[r for r in rows if r['subset']=='validation'])
    anchors=[next(r for r in rows if r['quality']==q) for q in ['failure','high_quality','intermediate']]
    atomic(REPAIR/'anchors.json',anchors)
    arms=[]
    def add(method,source,layer,alpha,**extra):
        arm=dict(method=method,source=source,layer=layer,steps=[4],k=8,alpha=alpha,tokens=list(range(8)),cap=.05,gate='none',**extra)
        arm['id']=f'{method}_{source}_l{layer}_a{alpha}_'+digest(arm)[:8];arms.append(arm)
    for layer in LAYERS:
        for source in ['n','p']:
            for method in ['mean','contract','ot']:
                for alpha in [.1,.25,.5,1.]:add(method,source,layer,alpha)
        for method in ['paired','local','linear','mlp','quality']:
            for alpha in [.5,1.]:add(method,'n' if method=='quality' else 'p',layer,alpha)
    for method in ['mean','contract','ot','paired']:
        for tok in [[5],[4,5,6]]:
            add(method,'p',17,.5,scope='local_token',tokens_override=tok)
            arms[-1]['tokens']=arms[-1].pop('tokens_override');arms[-1]['id']=digest(arms[-1])[:16]
    for step in [0,2]:
        for layer in [6,17]:
            for method in ['mean','contract','ot']:
                add(method,'n',layer,.5,step_override=step);arms[-1]['steps']=[arms[-1].pop('step_override')];arms[-1]['id']=digest(arms[-1])[:16]
    for method in ['random','reverse','random_subspace']:
        for layer in LAYERS:add(method,'p',layer,.5)
    # A budgeted continuous-layer and multi-step comparison.
    for method in ['mean','contract','ot']:
        add(method,'n',17,.5,multi_layers=[14,15,16,17])
        add(method,'n',17,.5,multi_steps=[0,1,2,3,4])
    atomic(REPAIR/'screen_arms.json',arms)
    protocol=dict(time=stamp(),stage='repair_v1',status='PREPARING',screen_counts=dict(Counter(r['quality'] for r in panel)),
        screen_in_sample_diagnostic=True,validation_samples=sum(r['subset']=='validation' for r in rows),methods=sorted({a['method'] for a in arms}),
        screen_arms=len(arms),fit_subset='exploration',base='frozen RL original checkpoint',scoring='original PDM after complete continuation',
        root_seed=20261008,validation_seeds=[0,1,2],nodes=2,gpus_per_node=16,dynamic_queue=True,
        thresholds=dict(failure_lt=.7,high_quality_gt=.9),test_access=False)
    atomic(REPAIR/'PROTOCOL.json',protocol)
    need={(s,l,a['k']) for a in arms for s in a.get('multi_steps',a['steps']) for l in a.get('multi_layers',[a['layer']])}
    for s,l,k in sorted(need):
        print(json.dumps(dict(stage='fit',step=s,layer=l,k=k)),flush=True)
        fit_site(l,s,k)
    atomic(REPAIR/'FITS_READY.json',dict(status='COMPLETE',time=stamp(),fits=len(need),arms=len(arms)))
    print(json.dumps(protocol),flush=True)

if __name__=='__main__':
    setup('repair/prepare');compatibility();import torch;torch.set_num_threads(1)
    prepare()
