"""Actual frozen suffixes and same-forward trajectory/interface capture."""
from r3_common import *
from functools import lru_cache


class Fits:
    def __init__(self,root): self.root=Path(root);self.values={};self.order=[]
    def get(self,arm):
        import numpy as np
        import torch
        path=Path(arm['fit_path']);path=path if path.is_absolute() else self.root/path
        key=(str(path),arm['fit_sha256'])
        if key not in self.values:
            assert sha(path)==key[1]
            with np.load(path,allow_pickle=False) as z:
                self.values[key]={n:torch.tensor(np.array(z[n]),device='cuda',dtype=torch.float32) for n in z.files}
            self.order.append(key)
            if len(self.order)>24:del self.values[self.order.pop(0)]
        return self.values[key]


def prediction(engine,features,hidden,j,token,interface=None,gradient=False,capture=True):
    import torch
    from common import reseed
    observed={}
    def hook(module,args,out):
        value=interface if interface is not None else out
        if capture:observed['interface']=value.detach().clone()
        return value
    handle=engine.agent.action_head.feature_encoder.register_forward_hook(hook)
    try:
        batch={k:v.unsqueeze(0).cuda().float() for k,v in features.items() if k not in ['pixel_values','last_hidden_state']}
        batch['last_hidden_state']=hidden;reseed(seed(token,j))
        with torch.set_grad_enabled(gradient),torch.autocast('cuda',enabled=False):
            value=engine.agent.forward(batch)['pred_traj'].squeeze(0)
        if capture:assert 'interface' in observed
        return value,observed.get('interface')
    finally:handle.remove()


def source_part(engine,part,fits):
    from r2_library_rollouts import apply,block
    value,statistics=apply(engine,part,fits);condition,post=engine.suffix(block(part),value)
    return condition,post,statistics


def joint(engine,config,features,hidden,j,token,fits):
    import torch
    from r2_behavior_router import base_trajectory,current_feature,checkpoint,coefficients
    from r2_mixed_locations_v3 import forward as mixture
    setting=config['configuration'];model=setting['model'];held=model.get('heldout_fold',-1)
    native,states=base_trajectory(engine,features,hidden,seed(token,j),True)
    module=checkpoint(setting['checkpoint']['path'],setting['checkpoint']['sha256'],model['input_dimension'],len(model['parts']))
    logits,amount=module(current_feature(engine,native,states,held,model['tier']))
    weights,strength=coefficients(logits,amount,model['kind']);strength=strength*setting.get('multiplier',1.)
    abstain=setting.get('force_Base',False) or bool(weights[0]>=setting.get('identity_threshold',1.01)) or (model['kind']=='hard_continuous' and int(weights.argmax())==0)
    if abstain:return hidden,None,dict(abstained=True)
    condition,post,statistics=mixture(engine,model['parts'],weights,strength,fits)
    return condition,post,dict(abstained=False,weights=weights.detach().cpu().tolist(),strengths=strength.detach().cpu().tolist())


def candidate_condition(engine,candidate,features,hidden,j,token,fit1,fit2):
    kind=candidate['kind'];spec=candidate['specification']
    if kind=='Base':return hidden,None,dict(relative_edit=0.)
    if kind=='batch1_upstream':
        changed,stats=engine.edited(spec,fit1.get(spec));condition,post=engine.suffix(spec['block'],changed)
        return condition,post,dict(relative_edit=float((stats[0]/stats[1].clamp(min=1e-12)).detach()))
    if kind in ['batch2_learned','batch2_delta','batch2_analytic']:
        return source_part(engine,spec,fit2)
    if kind=='batch2_policy_joint':return joint(engine,spec,features,hidden,j,token,fit2)
    raise ValueError('Runtime adapter not yet admitted: '+kind)


def init_scorer():
    import socket
    setup('scorers/'+socket.gethostname()+'/'+str(os.getpid()));compatibility()


def optimize(engine,features,target,token,noise_indices,block,group,cap,steps):
    """Return actual delta states; PDMS selection happens after real scoring."""
    import torch
    from r2_counterfactual import edited_value
    h=engine.prefix[block];mask,valid=engine.mask(block,group);assert valid
    selected=h.reshape(-1,h.shape[-1])[mask].float()
    radius=float(cap)*selected.norm().item()/len(selected)**.5
    delta=torch.nn.Parameter(torch.zeros(h.shape[-1],device='cuda'))
    optimizer=torch.optim.Adam([delta],lr=max(radius/h.shape[-1]**.5*.25,1e-6))
    records=[];parameters=[]
    for step in range(steps+1):
        optimizer.zero_grad(set_to_none=True)
        changed,stats=edited_value(engine,block,group,delta,cap);condition,post=engine.suffix(block,changed)
        losses=[]
        for j in noise_indices:
            trajectory,_=prediction(engine,features,condition,j,token,post,gradient=True,capture=False)
            scales=trajectory.new_tensor([40.,10.])
            losses.append(torch.nn.functional.smooth_l1_loss(trajectory[:,:2]/scales,target[:,:2]/scales)+.1*(1-torch.cos(trajectory[:,2]-target[:,2])).mean())
        loss=torch.stack(losses).mean();assert torch.isfinite(loss)
        if step==0 or step==steps or step%4==0:
            records.append(dict(step=step,surrogate_loss=float(loss.detach()),relative_edit=stats['relative_edit']))
            parameters.append(delta.detach().cpu().numpy().copy())
        if step<steps:
            loss.backward();assert delta.grad is not None and torch.isfinite(delta.grad).all();optimizer.step()
            with torch.no_grad():delta.mul_(torch.clamp(delta.new_tensor(radius)/delta.norm().clamp(min=1e-12),max=1.))
    return parameters,records
