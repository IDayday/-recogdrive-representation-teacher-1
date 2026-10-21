"""Inference-only activation editing, exact paired native RNG, and cached-prefix continuation."""
from common import *
from functools import lru_cache
import numpy as np

@lru_cache(maxsize=64)
def baseline_chunk(path):return read(path)

def baseline_row(row):
    i=row['global_index'];rank=i%32;offset=((i//32)//32)*32
    p=ROOT/'runs/rl_s0_20261016T063037Z/formal'/f'rank{rank:03d}'/'chunks'/f'{offset:06d}.json'
    return next(r for r in baseline_chunk(str(p))['records'] if r['token']==row['token'])

def trace(agent,features,value):
    import torch
    from paired_observation import conditions
    head=agent.action_head;cond=conditions(head,features);states=[];old=head.p_mean_variance
    def wrapped(x,*args,**kwargs):states.append(x.detach().clone());return old(x,*args,**kwargs)
    head.p_mean_variance=wrapped
    try:
        reseed(value)
        batch={k:v.unsqueeze(0).cuda().float() for k,v in features.items()}
        pred=agent.forward(batch)['pred_traj'].squeeze(0)
    finally:head.p_mean_variance=old
    reseed(value);initial=torch.randn((1,8,3),device='cuda');noise=[torch.randn_like(initial) for _ in range(5)]
    assert torch.equal(initial,states[0])
    return dict(cond=cond,states=states,noise=noise,trajectory=pred.detach().cpu().numpy())

class Editor:
    def __init__(self,head):
        self.head=head;self.fit={};self.step=0;self.metrics={};self.arm=None;self.handles=[];self.reference=None
        from paired_observation import modules
        for layer,(_,module) in enumerate(modules(head)):
            self.handles.append(module.register_forward_hook(self.make_hook(layer)))

    def load(self,step,layer,k):
        import torch
        key=(step,layer,k)
        if key not in self.fit:
            path=ROOT/'repair_v1/fits'/f's{step}_l{layer}_k{k}.npz'
            assert sha(path)==read(path.with_suffix('.json'))['sha256']
            with np.load(path,allow_pickle=False) as d:self.fit[key]={n:torch.tensor(d[n],device='cuda',dtype=torch.float32) for n in d.files}
            overlay=ROOT/'repair_v1/fits'/f'natural_learn_l{layer}_k{k}.npz'
            if step==4 and overlay.exists():
                assert sha(overlay)==read(overlay.with_suffix('.json'))['sha256']
                with np.load(overlay,allow_pickle=False) as d:self.fit[key].update({n:torch.tensor(d[n],device='cuda',dtype=torch.float32) for n in d.files})
        return self.fit[key]

    def make_hook(self,layer):
        def hook(module,inputs,h):
            if self.arm is None:return
            a=self.arm;layers=a.get('multi_layers',[a['layer']]);steps=a.get('multi_steps',a['steps'])
            if layer not in layers or self.step not in steps:return
            import torch
            f=self.load(self.step,layer,a['k']);result=h.clone();changes=[]
            benefit_gate=None
            if a['gate']=='benefit':
                if not hasattr(self,'benefit_cache'):self.benefit_cache={}
                gp=a['benefit_path']
                if gp not in self.benefit_cache:
                    with np.load(ROOT/gp,allow_pickle=False) as d:self.benefit_cache[gp]={n:torch.tensor(d[n],device='cuda',dtype=torch.float32) for n in d.files}
                gf=self.benefit_cache[gp]
                zz=torch.cat([(h[0,j]-f[f'n_{j}_center'])@f[f'n_{j}_b'] for j in range(8)])
                utility=((zz-gf['mean'])/gf['scale'])@gf['weights']+gf['intercept']
                benefit_gate=(utility>float(a.get('benefit_threshold',0.))).float()
            for tok in a['tokens']:
                s=a['source'];prefix=f'{s}_{tok}_';b=f[prefix+'b'];center=f[prefix+'center']
                z=(h[0,tok]-center)@b;mh=f[prefix+'mh'];ml=f[prefix+'ml'];scale=f[prefix+'scale'];method=a['method']
                if method in ['patch','patch_full']:
                    if self.reference is None:dz=torch.zeros_like(z)
                    else:dz=(self.reference[layer,tok]-h[0,tok])@b
                elif method in ['mean','paired','reverse','random','random_subspace']:
                    dz=mh-ml
                    if method=='reverse':dz=-dz
                    if method=='random':
                        # Fixed deterministic direction; does not consume the native sampling stream.
                        u=torch.sin(torch.arange(len(dz),device='cuda')+layer*31+tok*7+.3)
                        dz=u/u.norm()*dz.norm()
                elif method=='contract':dz=mh-z
                elif method=='soft_clip':dz=torch.clamp(z-mh,min=-2*scale,max=2*scale)-(z-mh)
                elif method=='ot':dz=mh+(z-ml)@f[prefix+'a'].T-z
                elif method in ['linear','mlp']:
                    xx=(z-f[prefix+'zm'])/f[prefix+'zs']
                    if method=='linear':dz=torch.cat([xx,xx.new_ones(1)])@f[prefix+'reg']
                    else:
                        mid=torch.tanh(xx@f[prefix+'mlp_0.weight'].T+f[prefix+'mlp_0.bias'])
                        dz=(mid@f[prefix+'mlp_2.weight'].T+f[prefix+'mlp_2.bias'])*scale
                elif method=='local':
                    low=f[prefix+'local_low'];delta=f[prefix+'local_delta'];distance=(((low-z)/scale)**2).mean(1)
                    v,idx=torch.topk(distance,min(16,len(distance)),largest=False);w=torch.softmax(-v,0)
                    dz=(w[:,None]*delta[idx]).sum(0)
                elif method=='quality':
                    dz=f[f'n_{tok}_critic'];dz=dz/dz.norm().clamp(min=1e-8)*scale.norm()
                else:raise ValueError(method)
                gate=1.
                if a['gate']=='benefit':gate=benefit_gate
                elif a['gate']!='none':
                    nb=f[f'n_{tok}_b'];nz=(h[0,tok]-f[f'n_{tok}_center'])@nb
                    risk=((nz-f[f'n_{tok}_risk_origin'])*f[f'n_{tok}_risk']).sum()
                    threshold=float(a.get('gate_threshold',2.326))
                    gate=torch.sigmoid((risk-threshold)*4) if a['gate']=='soft' else (risk>threshold).float()
                if method=='patch_full' and self.reference is not None:
                    dh=self.reference[layer,tok]-h[0,tok]
                elif method=='random_subspace':
                    # Orthonormal deterministic alternative basis, equal hidden-space pre-cap norm.
                    ii=torch.arange(384,device='cuda')[:,None];jj=torch.arange(b.shape[1],device='cuda')[None,:]
                    qb=torch.linalg.qr(torch.sin(ii*(jj+1)*.173+layer+.71),mode='reduced')[0]
                    dh=qb@dz
                else:dh=b@dz
                dh=dh*(a['alpha']*gate/max(np.sqrt(len(layers)*len(steps)),1.))
                limit=a['cap']*h[0,tok].norm();factor=torch.clamp(limit/dh.norm().clamp(min=1e-12),max=1.)
                dh=dh*factor;result[0,tok]=h[0,tok]+dh
                changes.append(torch.stack([dh.norm(),h[0,tok].norm(),torch.as_tensor(gate,device='cuda'),factor]))
            if changes:self.metrics[(self.step,layer)]=torch.stack(changes).detach()
            return result
        return hook

    def set_reference(self,token):
        import torch
        if not hasattr(self,'paired_reference_cache'):
            cache=ROOT/'analysis/observation_v1/cache'
            self.paired_reference_cache=np.load(cache/'hidden_P0.npy',mmap_mode='r')
            self.paired_reference_q=np.load(cache/'scores.npy')[0]
            self.paired_reference_index={r['token']:i for i,r in enumerate(read(cache/'metadata.json'))}
        i=self.paired_reference_index.get(token);self.reference=None
        if i is not None:
            branch=int(np.argmax(self.paired_reference_q[i]))
            if self.paired_reference_q[i,branch]>.9:
                self.reference=torch.tensor(np.array(self.paired_reference_cache[i,branch]),device='cuda',dtype=torch.float32)
        return self.reference is not None

    def predict(self,chain,arm,gradient=False):
        import torch
        head=self.head;self.arm=arm;self.metrics={}
        steps=arm.get('multi_steps',arm['steps']);start=0 if arm.get('from_start',False) else min(steps);x=chain['states'][start].clone()
        try:
            for i in range(start,5):
                self.step=i;t=head.make_timesteps(1,head.ddim_t[i],x.device);idx=head.make_timesteps(1,i,x.device)
                mean,lv,_=head.p_mean_variance(x,t,idx,*chain['cond'],deterministic=False)
                x=mean+torch.exp(.5*lv).float().clamp(min=.0001)*chain['noise'][i].clamp(-1,1)
            out=head.denorm_odo(x.clamp(-1,1)).squeeze(0)
            z=torch.cat(list(self.metrics.values())) if self.metrics else x.new_zeros((1,4))
            m=dict(edit_norm=float(z[:,0].square().sum().sqrt()),relative_edit_max=float((z[:,0]/z[:,1].clamp(min=1e-8)).max()),
                   gate_mean=float(z[:,2].mean()),cap_fraction=float((z[:,3]<.9999).float().mean()),sites=len(self.metrics))
            return out.detach().cpu().numpy(),m
        finally:self.arm=None

    def close(self):
        for handle in self.handles:handle.remove()

def geometries(pred,baseline):
    d=pred-baseline
    return dict(trajectory_displacement_mean_m=float(np.linalg.norm(d[:,:2],axis=1).mean()),
        trajectory_displacement_max_m=float(np.linalg.norm(d[:,:2],axis=1).max()),
        heading_change_max=float(np.abs(d[:,2]).max()),
        second_difference_change_max_m=float(np.linalg.norm(np.diff(d[:,:2],n=2,axis=0),axis=1).max()))
