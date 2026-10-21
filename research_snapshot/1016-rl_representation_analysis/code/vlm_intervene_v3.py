"""Equivalent private engine: cache group indices and invariant interface projection."""
from vlm_intervene_v2 import Engine as PriorEngine

class Engine(PriorEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._feature_forward=self.agent.action_head.feature_encoder.forward;self.index_cache={};self.projection_hidden=None;self.projection_value=None

    def forward_native(self,features):
        self.index_cache={};self.projection_hidden=None;self.projection_value=None
        return super().forward_native(features)

    def mask(self,block,group):
        import torch
        key=(('vision' if block.startswith('vision') else 'bridge' if block.startswith('bridge') else 'language'),group)
        if key not in self.index_cache:
            mask,valid=super().mask(block,group);self.index_cache[key]=(torch.nonzero(mask,as_tuple=False).flatten(),valid)
        return self.index_cache[key]

    def trajectory(self,features,hidden,value,interface=None):
        if interface is None:
            if hidden is not self.projection_hidden:
                self.projection_hidden=hidden;self.projection_value=self._feature_forward(hidden)
            projected=self.projection_value
        else:projected=interface
        layer=self.agent.action_head.feature_encoder;layer.forward=lambda inputs:projected
        try:return super().trajectory(features,hidden,value,interface=None)
        finally:layer.forward=self._feature_forward
