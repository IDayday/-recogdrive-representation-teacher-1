"""Exact cached interface state, including the actual 2800-token padding mask.

Restricted to interface_pre/post. It never fabricates earlier-layer activations.
Prompt/token/mask reconstruction is verified against the raw VLM path in smoke.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def counts():
    import numpy as np
    meta=read(ROOT/'manifests/PATCH_COUNTS.json');assert sha(ROOT/meta['path'])==meta['sha256']
    with np.load(ROOT/meta['path']) as z:return np.array(z['counts'])


def from_cached(engine,features,index):
    import torch
    from vlm_core import question,language_masks
    from model.recogdrive_backbone import system_message,IMG_START_TOKEN,IMG_CONTEXT_TOKEN,IMG_END_TOKEN
    from model.utils.conversation import get_conv_template
    patches=int(counts()[index]);q=question(features)
    template=get_conv_template('internvl2_5');template.system_message=system_message
    template.append_message(template.roles[0],q);template.append_message(template.roles[1],None)
    query=template.get_prompt().replace('<image>',IMG_START_TOKEN+IMG_CONTEXT_TOKEN*256*patches+IMG_END_TOKEN,1)
    engine.backbone.tokenizer.padding_side='left'
    encoded=engine.backbone.tokenizer([query],return_tensors='pt',padding='max_length',max_length=2800)
    ids=encoded['input_ids'].cuda();attention=encoded['attention_mask'].cuda()
    hidden=features['last_hidden_state'].unsqueeze(0).cuda().float()
    assert hidden.shape[1]==ids.shape[1]
    engine.lm=language_masks(engine.backbone,ids,attention,patches)
    engine.hidden=hidden;engine.prefix={'interface_pre':hidden,'interface_post':engine.agent.action_head.feature_encoder(hidden).detach()}
    engine.inputs=dict(input_ids=ids,attention_mask=attention,cached_interface_only=True)
    engine.kwargs={};engine.collect=False;engine.keep=False
    return hidden
