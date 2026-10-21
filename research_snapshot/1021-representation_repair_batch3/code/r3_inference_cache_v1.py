"""Exact memoization of frozen constant cross-attention context projections.

No batching, precision, RNG or model parameter changes. Caches require the same
input tensor object within one fixed intervention; different inputs recompute.
The current frozen first42 run does not import or use this experimental helper.
"""
from contextlib import contextmanager


@contextmanager
def constant_context(engine,verify=False):
    import torch
    head=engine.agent.action_head;modules=[('feature_encoder',head.feature_encoder)]
    for i,block in enumerate(head.model.transformer_blocks):
        attn=block.attn
        if getattr(attn,'is_cross_attention',False):modules.extend([(f'cross_{i}_k',attn.to_k),(f'cross_{i}_v',attn.to_v)])
    stats=dict(modules=len(modules),calls=0,hits=0,misses=0,verified_hits=0);restore=[]
    assert not head.training
    try:
        for name,module in modules:
            original=module.forward;had_instance='forward' in module.__dict__;old_instance=module.__dict__.get('forward');memo={}
            def forward(value,*args,_original=original,_memo=memo,**kwargs):
                stats['calls']+=1
                if not args and not kwargs and _memo.get('input') is value:
                    stats['hits']+=1
                    if verify:
                        expected=_original(value);assert torch.equal(expected,_memo['output']);stats['verified_hits']+=1
                    return _memo['output']
                result=_original(value,*args,**kwargs);stats['misses']+=1
                if not args and not kwargs:_memo.update(input=value,output=result)
                return result
            restore.append((module,had_instance,old_instance));module.forward=forward
        yield stats
    finally:
        for module,had,value in reversed(restore):
            if had:module.forward=value
            else:delattr(module,'forward')
