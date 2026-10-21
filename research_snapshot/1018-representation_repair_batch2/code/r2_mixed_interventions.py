"""Differentiable mixtures with an exact identity expert and explicit site order.

At a shared site every component reads the same current tensor; weighted deltas
are summed before continuing the network. Across sites, actual network execution
determines the nonlinear interaction. There is no sqrt(K) scaling or trajectory
coordinate averaging. Soft policies must be trained and rescored as mixtures.
"""
from r2_common import *


def component_value(engine,part,fits,value):
    from r2_learned_expert import apply
    if part['kind']=='analytic':block=part['arm']['block']
    else:block=part['training_task']['block']
    previous=engine.prefix[block];engine.prefix[block]=value
    try:
        if part['kind']=='analytic':return engine.edited(part['arm'],fits.get(part['arm']))[0]
        return apply(engine,part['training_task'],part['checkpoint'],1.)[0]
    finally:engine.prefix[block]=previous


def block_name(part):
    return part['arm']['block'] if part['kind']=='analytic' else part['training_task']['block']


def block_cap(part):
    return part['arm']['cap'] if part['kind']=='analytic' else part['training_task']['cap']


def mixed_forward(engine,parts,weights,fits,strengths=None):
    """weights[0] is the do-nothing expert; the remainder need not sum to one."""
    import torch
    assert len(weights)==len(parts)+1
    weights=torch.as_tensor(weights,device='cuda',dtype=torch.float32)
    assert bool(torch.isfinite(weights).all()) and bool((weights>=0).all())
    assert bool(weights.sum()<=1.000001)
    if strengths is None:strengths=torch.ones(len(parts),device='cuda')
    strengths=torch.as_tensor(strengths,device='cuda',dtype=torch.float32)
    assert len(strengths)==len(parts) and bool((strengths>=0).all()) and bool((strengths<=2).all())
    grouped={};stats=[];handles=[]
    for i,part in enumerate(parts):grouped.setdefault(block_name(part),[]).append((i,part))

    def change(block,value):
        # Mixture components share this value, rather than being applied as an
        # arbitrary sequence of operators at the same module.
        original=value.float();delta=torch.zeros_like(original);radius=original.new_zeros(())
        for i,part in grouped[block]:
            changed=component_value(engine,part,fits,value)
            component=changed.float()-original
            coefficient=weights[i+1]*strengths[i]
            delta=delta+coefficient*component
            radius=radius+coefficient*component.norm()
        shift=delta
        for _ in range(4):
            trial=(original+shift).to(value.dtype)
            norm=(trial.float()-original).norm()
            shift=shift*torch.clamp(radius/norm.detach().clamp(min=1e-12)*.999,max=1.)
        trial=(original+shift).to(value.dtype)
        norm=(trial.float()-original).norm()
        trial=torch.where(norm.detach()<=radius.detach()+1e-7,trial,value)
        stats.append(torch.stack([(trial.float()-original).norm(),original.norm(),radius,weights[1:].sum()]))
        return trial

    def attach(block):
        if block in ['interface_pre','interface_post']:return
        if block in ['bridge_pre','language_input']:
            module=engine.model.mlp1[0] if block=='bridge_pre' else engine.model.language_model.model.layers[0]
            handles.append(module.register_forward_pre_hook(lambda m,a,block=block:(change(block,a[0]),*a[1:])))
            return
        if block=='vision_embedding':module=engine.model.vision_model.embeddings
        elif block.startswith('vision_'):module=engine.model.vision_model.encoder.layers[int(block.split('_')[1])]
        elif block.startswith('bridge_'):module=engine.model.mlp1[int(block.split('_')[1])]
        elif block=='language_norm':module=engine.model.language_model.model.norm
        else:module=engine.model.language_model.model.layers[int(block.split('_')[1])]
        def hook(m,a,out,block=block):
            value=out[0] if isinstance(out,tuple) else out;changed=change(block,value)
            return (changed,*out[1:]) if isinstance(out,tuple) else changed
        handles.append(module.register_forward_hook(hook))
    engine.collect=False;engine.keep=False
    try:
        for block in grouped:attach(block)
        hidden=engine.model(**engine.inputs).hidden_states[-1].float()
    finally:
        for handle in handles:handle.remove()
    # Explicit ordering avoids conflating BF16 language-norm output with the
    # FP32 interface-pre tensor used by single-site native continuation.
    if 'interface_pre' in grouped:hidden=change('interface_pre',hidden)
    interface=None
    if 'interface_post' in grouped:
        interface=engine.agent.action_head.feature_encoder(hidden)
        interface=change('interface_post',interface)
    return hidden,interface,stats
