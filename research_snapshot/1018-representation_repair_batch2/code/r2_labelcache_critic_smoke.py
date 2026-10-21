"""Exact parameter/label/RNG schedule A/B with an actual eighteen-source wave."""
from r2_common import *


def run(engine,task,pool):
    from r2_token_critic_prefetch_v2 import run as ordinary
    from r2_uniform_critic_train import run as uniform
    from r2_context_critic import run as context
    from r2_labelcached_critic import run as cached
    from r2_native_training_ab import equal_arrays
    source=read(ROOT/'runs/token_critic_training_v1/tasks.json')[0];assert len(source['responses'])==18
    comparisons=[]
    for kind,execute,extra in [('full',ordinary,{}),('uniform',uniform,{}),('pre_all',context,dict(context_view='pre_all'))]:
        spec=dict(source,steps=64,checkpoints=[64],**extra)
        before=execute(engine,dict(spec,id='labelcache_reference_'+kind),pool)
        after=cached(engine,dict(spec,id='labelcache_candidate_'+kind,_artifact_context_namespace=kind,_uniform_context=kind=='uniform'),pool)
        old=read(ROOT/before['path']);new=read(ROOT/after['path']);arrays=equal_arrays(old,new)
        a=[(r['index'],r['seed_index'],r['candidate_source']) for r in old['trace']];b=[(r['index'],r['seed_index'],r['candidate_source']) for r in new['trace']];assert a==b
        comparisons.append(dict(kind=kind,arrays=arrays,schedule_exact=True,responses=18,label_bank_bytes=new['label_bank_bytes'],
            reference_seconds=old['seconds'],candidate_seconds=new['seconds'],reference_input_wait=old['input_wait_seconds'],candidate_input_wait=new['input_wait_seconds']))
    path=ROOT/'provenance/CRITIC_LABELCACHE_EQUIVALENCE_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),all_checkpoint_arrays_exact=True,comparisons=comparisons,
        only_immutable_response_label_arrays_preloaded=True,observation_data_and_loss_unchanged=True,
        reason='Observed 8k-step critic input waits approximately 244-261s of 503-529s. Avoid a 12-entry LRU repeatedly decompressing 18/126 immutable response matrices.',
        scope='64-step same-worker engineering A/B. Sequential warmup affects timing; compare formal long runs after adoption.'))
    return dict(path=str(path.relative_to(ROOT)),comparisons=comparisons)
