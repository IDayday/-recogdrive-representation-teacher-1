"""Expose the exact existing Base ego/history conditions to a frozen-token critic.

No extra observations: these encoders already condition every action-head call.
Equal-length zero tokens control the added attention mass and parameter count.
"""
def append(engine,features,context,mode):
    import torch
    assert mode in ['actual','zero']
    with torch.no_grad():
        head=engine.agent.action_head
        history=features['history_trajectory'].to(device='cuda',dtype=torch.float32).reshape(1,1,12)
        status=features['status_feature'].to(device='cuda',dtype=torch.float32).reshape(1,8)
        h=head.his_traj_encoder(history).reshape(-1,context.shape[-1])
        e=head.ego_status_encoder(status).reshape(-1,context.shape[-1])
        aux=torch.cat([h,e],0).detach();assert aux.ndim==2 and aux.shape[1]==context.shape[1] and torch.isfinite(aux).all()
        if mode=='zero':aux=torch.zeros_like(aux)
        return torch.cat([context,aux],0)
