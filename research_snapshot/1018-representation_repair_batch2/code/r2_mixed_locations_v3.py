"""Actual differentiable mixtures across frozen vision/language/interface sites.

Experts at a common site read the same current activation. Cross-site effects
follow the actual network, including changes reaching a later expert. This is
not a sum of independently measured trajectory gains.
"""
from r2_common import *


def forward(engine,parts,weights,strengths,fits):
    import torch
    from r2_library_rollouts import block
    from r2_mixed_interfaces_v2 import component,forward as interfaces
    if all(block(p) in ['interface_pre','interface_post'] for p in parts):
        return interfaces(engine,parts,weights,strengths,fits)
    assert len(weights)==len(parts)+1 and len(strengths)==len(parts)
    grouped={};stats=[];handles=[]
    for i,p in enumerate(parts):grouped.setdefault(block(p),[]).append((i,p))

    def change(site,value):
        original=value.float();delta=torch.zeros_like(original);radius=original.new_zeros(())
        for i,part in grouped[site]:
            shift=component(engine,part,value,fits).float()-original
            coefficient=weights[i+1]*strengths[i]
            delta=delta+coefficient*shift;radius=radius+coefficient*shift.norm()
        for _ in range(3):
            trial=(original+delta).to(value.dtype);norm=(trial.float()-original).norm()
            factor=torch.clamp(radius/norm.detach().clamp(min=1e-12)*.999,max=1.)
            factor=torch.where(radius.detach()>1e-12,factor,torch.ones_like(factor));delta=delta*factor
        trial=(original+delta).to(value.dtype);norm=(trial.float()-original).norm()
        trial=torch.where(norm.detach()<=radius.detach()+1e-7,trial,value)
        stats.append(torch.stack([(trial.float()-original).norm(),original.norm(),radius]))
        return trial

    def attach(site):
        if site in ['interface_pre','interface_post']:return
        if site in ['bridge_pre','language_input']:
            module=engine.model.mlp1[0] if site=='bridge_pre' else engine.model.language_model.model.layers[0]
            def pre(module,args,kwargs,site=site):
                if args:return (change(site,args[0]),*args[1:]),kwargs
                assert 'hidden_states' in kwargs
                return args,dict(kwargs,hidden_states=change(site,kwargs['hidden_states']))
            handles.append(module.register_forward_pre_hook(pre,with_kwargs=True));return
        if site=='vision_embedding':module=engine.model.vision_model.embeddings
        elif site.startswith('vision_'):module=engine.model.vision_model.encoder.layers[int(site.split('_')[1])]
        elif site.startswith('bridge_'):module=engine.model.mlp1[int(site.split('_')[1])]
        elif site=='language_norm':module=engine.model.language_model.model.norm
        else:
            assert site.startswith('language_'),site
            module=engine.model.language_model.model.layers[int(site.split('_')[1])]
        def hook(module,args,out,site=site):
            value=out[0] if isinstance(out,tuple) else out;changed=change(site,value)
            return (changed,*out[1:]) if isinstance(out,tuple) else changed
        handles.append(module.register_forward_hook(hook))

    engine.collect=False;engine.keep=False
    try:
        for site in grouped:attach(site)
        hidden=engine.model(**engine.inputs).hidden_states[-1].float()
    finally:
        for handle in handles:handle.remove()
    if 'interface_pre' in grouped:hidden=change('interface_pre',hidden)
    post=None
    if 'interface_post' in grouped:
        post=change('interface_post',engine.agent.action_head.feature_encoder(hidden))
    assert len(stats)==len(grouped),set(grouped)
    return hidden,post,stats
