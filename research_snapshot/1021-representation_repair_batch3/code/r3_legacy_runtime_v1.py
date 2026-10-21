"""Legacy interventions during the complete actual native forward.

Prepared adapter only: runtime admission requires comparison with the original
prefix-continuation editors before using it in formal expansion.
"""
from r3_common import *


def prediction(engine,arm,features,hidden,token,j):
    import numpy as np
    import torch
    from r3_runtime import prediction as native
    if arm['method']=='trajectory_scale':
        from repair_postprocess import scale_trajectory
        trajectory,interface=native(engine,features,hidden,j,token)
        result=scale_trajectory(trajectory.cpu().numpy(),arm['factor'])
        return torch.tensor(result,device='cuda'),interface,dict(relative_edit=0.,interface_modified=False,trajectory_postprocessing=True,factor=arm['factor'])
    actual=arm['legacy_arm'] if arm['method']=='legacy' else arm
    if 'fit' in actual or 'components' in actual:
        from candidate_repair_engine import CandidateEditor
        editor=CandidateEditor(engine.agent.action_head);expanded=True;editor.metrics=[]
    else:
        from repair_engine import Editor
        editor=Editor(engine.agent.action_head);expanded=False;editor.metrics={}
    editor.arm=actual;counter=[0];head=engine.agent.action_head;original=head.p_mean_variance
    def step(*args,**kwargs):
        editor.step=counter[0];counter[0]+=1
        return original(*args,**kwargs)
    had_instance='p_mean_variance' in head.__dict__;old_instance=head.__dict__.get('p_mean_variance')
    head.p_mean_variance=step
    try:
        trajectory,interface=native(engine,features,hidden,j,token)
        assert counter[0]==5
        if expanded:
            metrics=editor.metrics
            relative=max([float(torch.stack([v[0]/v[1].clamp(min=1e-8) for t,v in metrics if t==tok]).square().sum().sqrt()) for tok in {t for t,_ in metrics}] or [0.])
        else:
            values=torch.cat(list(editor.metrics.values())) if editor.metrics else hidden.new_zeros((1,4))
            relative=float((values[:,0]/values[:,1].clamp(min=1e-8)).max())
        assert relative<=float(actual['cap'])+1e-6
        return trajectory,interface,dict(relative_edit=relative,interface_modified=False,actual_native_full_forward=True)
    finally:
        if had_instance:head.p_mean_variance=old_instance
        else:delattr(head,'p_mean_variance')
        editor.arm=None;editor.close()
