"""Same full-token critic architecture/data/loss, context restricted to mean.

Both attention Q/K projections are identically zero and remain frozen at zero;
attention is uniform for every candidate. Remaining weights, initializations and
sampling schedule match the conditional-attention critic exactly. Existing model
loaders can evaluate the identical parameter schema without a special shortcut.
"""
from r2_common import *


def make_model():
    import torch
    from r2_token_critic import make_model as full
    model=full()
    for attention in model.attention:
        with torch.no_grad():attention.in_proj_weight[:256].zero_();attention.in_proj_bias[:256].zero_()
        attention.in_proj_weight.register_hook(lambda g:torch.cat([torch.zeros_like(g[:256]),g[256:]],0))
        attention.in_proj_bias.register_hook(lambda g:torch.cat([torch.zeros_like(g[:256]),g[256:]],0))
    return model
