"""Exact native-noise continuation with edits in frozen expanded candidate spaces."""
from common import *
import numpy as np
from repair_engine import geometries

class CandidateEditor:
    def __init__(self,head):
        from paired_observation import modules
        self.head=head;self.arm=None;self.step=0;self.fit={};self.gates={};self.metrics=[]
        named=modules(head)+[('dit_output',head.model.final_layer)]
        self.handles=[module.register_forward_hook(self.hook(layer)) for layer,(_,module) in enumerate(named)]

    def load(self,fit_id):
        import torch
        if fit_id not in self.fit:
            p=ROOT/'candidate_repair_v1/fits'/(fit_id+'.npz');spec=read(p.with_suffix('.json'));assert sha(p)==spec['fit_sha256']
            with np.load(p) as d:self.fit[fit_id]={k:torch.tensor(d[k],dtype=torch.float32,device='cuda') for k in d.files if k!='native_indices'}
        return self.fit[fit_id]

    def hook(self,layer):
        def edit(module,inputs,h):
            if self.arm is None:return
            import torch
            components=self.arm.get('components',[self.arm]);matching=[a for a in components if a['layer']==layer and a['step']==self.step]
            if not matching:return
            result=h.clone()
            for a in matching:
                f=self.load(a['fit']);tok=a['token'];original=result[0,tok].clone();z=(original-f['center'])@f['b'];pre=a.get('calibration','p')
                mh=f[pre+'_mh'];ml=f[pre+'_ml'];method=a['method'];scale=f[pre+'_scale']
                if method in ['mean','reverse','random_direction']:
                    dz=mh-ml
                    if method=='reverse':dz=-dz
                elif method=='contract':dz=mh-z
                elif method=='boundary':
                    gap=ml-mh;amount=torch.clamp(((z-mh)*gap).sum()/gap.square().sum().clamp(min=1e-12),min=0.)
                    dz=-amount*gap
                elif method=='ot':dz=mh+(z-ml)@f[pre+'_ot'].T-z
                elif method in ['linear','mlp','linear_replay','mlp_replay']:
                    label='replay' if method.endswith('_replay') else 'paired';xx=(z-f[label+'_zm'])/f[label+'_zs']
                    if method.startswith('linear'):dz=torch.cat([xx,xx.new_ones(1)])@f[label+'_reg']
                    else:
                        mid=torch.tanh(xx@f[label+'_mlp_0.weight'].T+f[label+'_mlp_0.bias'])
                        dz=(mid@f[label+'_mlp_2.weight'].T+f[label+'_mlp_2.bias'])*f['p_scale']
                elif method=='local':
                    distance=(((f['local_low']-z)/scale)**2).mean(1);v,idx=torch.topk(distance,min(16,len(distance)),largest=False)
                    dz=(torch.softmax(-v,0)[:,None]*f['local_delta'][idx]).sum(0)
                else:raise ValueError(method)
                risk=((z-f['risk_origin'])*f['risk']).sum();gate=z.new_ones(())
                if a['gate'].startswith('risk'):gate=(risk>f[a['gate']]).float()
                elif a['gate']=='benefit':
                    gp=a['benefit_path']
                    if gp not in self.gates:
                        assert sha(ROOT/gp)==read((ROOT/gp).with_suffix('.json'))['sha256']
                        with np.load(ROOT/gp) as d:self.gates[gp]={k:torch.tensor(d[k],dtype=torch.float32,device='cuda') for k in d.files}
                    g=self.gates[gp];utility=((z-g['mean'])/g['scale'])@g['weight']+g['intercept']
                    gate=(utility>a.get('benefit_threshold',0.)).float()
                dh=f['b']@dz
                if a.get('control_kind')=='haar_rotation':
                    # Same parent correction, gate and pre-cap norm; only orientation changes.
                    dh=self.load(a['alternative_basis'])['b']@dz
                elif a.get('control_kind')=='reverse':dh=-dh
                elif a.get('control_kind') in ['full_mean','equal_mean']:
                    other=self.load(a['alternative_basis']);raw=other['b']@(other[pre+'_mh']-other[pre+'_ml'])
                    dh=raw/raw.norm().clamp(min=1e-12)*dh.norm()
                if method=='random_direction':
                    # Precomputed CPU Gaussian direction never consumes native sampling RNG.
                    direction=z.new_tensor(a['random_direction']);dh=direction/direction.norm()*dh.norm()
                dh=dh*(a['alpha']*gate);limit=a['cap']/np.sqrt(len(components))*original.norm()
                factor=torch.clamp(limit/dh.norm().clamp(min=1e-12),max=1.);dh*=factor
                result[0,tok]=original+dh
                self.metrics.append((tok,torch.stack([dh.norm(),original.norm(),gate,factor,risk]).detach()))
            return result
        return edit

    def predict(self,chain,arm):
        import torch
        self.arm=arm;self.metrics=[];components=arm.get('components',[arm]);start=0 if arm.get('from_start') else min(a['step'] for a in components)
        head=self.head;x=chain['states'][start].clone()
        try:
            for i in range(start,5):
                self.step=i;t=head.make_timesteps(1,head.ddim_t[i],x.device);idx=head.make_timesteps(1,i,x.device)
                mean,lv,_=head.p_mean_variance(x,t,idx,*chain['cond'],deterministic=False)
                x=mean+torch.exp(.5*lv).float().clamp(min=.0001)*chain['noise'][i].clamp(-1,1)
            out=head.denorm_odo(x.clamp(-1,1)).squeeze(0)
            values=torch.stack([v for _,v in self.metrics]) if self.metrics else x.new_zeros((1,5))
            relative=values[:,0]/values[:,1].clamp(min=1e-8)
            aggregate=max([float(torch.stack([v[0]/v[1].clamp(min=1e-8) for t,v in self.metrics if t==tok]).square().sum().sqrt()) for tok in {t for t,_ in self.metrics}] or [0.])
            result=dict(edit_norm=float(values[:,0].square().sum().sqrt()),relative_edit_max=float(relative.max()),relative_edit_l2_max=aggregate,
                gate_mean=float(values[:,2].mean()),cap_fraction=float((values[:,3]<.9999).float().mean()),sites=len(self.metrics))
            assert aggregate<=max(a['cap'] for a in components)+1e-6,(arm['id'],aggregate,[a['cap'] for a in components])
            return out.detach().cpu().numpy(),result
        finally:self.arm=None

    def close(self):
        for handle in self.handles:handle.remove()
