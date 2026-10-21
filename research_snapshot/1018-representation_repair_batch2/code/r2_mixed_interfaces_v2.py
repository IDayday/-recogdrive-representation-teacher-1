"""Differentiable, cached interface mixtures; components read the same site state.

Independent version of the already verified mixed intervention. Selected expert
strength is respected. A zero mixture is bitwise native, and no outcome additivity
is assumed. Only interface sites are accepted; other locations use the raw path.
"""
from r2_common import *


def component(engine,part,value,fits):
    import torch
    from r2_library_rollouts import block,apply
    from r2_learned_expert import checkpoint_arrays
    from r2_learned_expert_v3 import edit
    location=block(part);previous=engine.prefix[location];engine.prefix[location]=value
    try:
        if part['kind']!='learned':return apply(engine,part,fits)[0]
        task=part['training_task'];checkpoint=part['checkpoint']
        arrays=checkpoint_arrays(checkpoint['path'],checkpoint['sha256'])
        mask,valid=engine.mask(location,task['group']);assert valid
        pooled=value.reshape(-1,value.shape[-1])[mask].float().mean(0)
        z=(pooled-arrays['center'])@arrays['basis']/arrays['scale']
        z=torch.nn.functional.linear(torch.tanh(torch.nn.functional.linear(z,arrays['down.weight'],arrays['down.bias'])),arrays['up.weight'],arrays['up.bias'])
        strength=part.get('strength',1.)
        return edit(engine,location,task['group'],arrays['basis']@z*strength,task['cap']*strength)[0]
    finally:engine.prefix[location]=previous


def forward(engine,parts,weights,strengths,fits):
    import torch
    from r2_library_rollouts import block
    assert len(weights)==len(parts)+1 and len(strengths)==len(parts)
    grouped={};stats=[]
    for i,part in enumerate(parts):
        site=block(part);assert site in ['interface_pre','interface_post']
        grouped.setdefault(site,[]).append((i,part))
    def change(site,value):
        original=value.float();delta=torch.zeros_like(original);radius=original.new_zeros(())
        for i,part in grouped.get(site,[]):
            shift=component(engine,part,value,fits).float()-original
            coefficient=weights[i+1]*strengths[i]
            delta=delta+coefficient*shift;radius=radius+coefficient*shift.norm()
        # The norm of a mixture may be smaller by cancellation. Its true effect
        # is evaluated downstream, not inferred from the component response table.
        for _ in range(3):
            trial=(original+delta).to(value.dtype);norm=(trial.float()-original).norm()
            multiplier=torch.clamp(radius/norm.detach().clamp(min=1e-12)*.999,max=1.)
            multiplier=torch.where(radius.detach()>1e-12,multiplier,torch.ones_like(multiplier))
            delta=delta*multiplier
        trial=(original+delta).to(value.dtype);norm=(trial.float()-original).norm()
        trial=torch.where(norm.detach()<=radius.detach()+1e-7,trial,value)
        stats.append(torch.stack([(trial.float()-original).norm(),original.norm(),radius]))
        return trial
    hidden=engine.prefix['interface_pre']
    if 'interface_pre' in grouped:hidden=change('interface_pre',hidden)
    interface=None
    if 'interface_post' in grouped:
        interface=engine.agent.action_head.feature_encoder(hidden)
        interface=change('interface_post',interface)
    return hidden,interface,stats
