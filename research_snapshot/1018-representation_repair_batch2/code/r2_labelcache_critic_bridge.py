"""Verified immutable label preload, independent artifacts, same canonical task."""
from r2_common import *


def run(engine,task,pool):
    from r2_labelcached_critic import run as execute
    assert read(ROOT/'provenance/CRITIC_LABELCACHE_EQUIVALENCE_PASS.json')['all_checkpoint_arrays_exact']
    stage=Path(task['stage']).name if task.get('stage') else ''
    if task['id'].startswith('uniform_'):
        namespace='uniform';canonical=ROOT/'pooled_token_critics'/task['id']/'TRAINING.json';uniform=True
    elif 'context_view' in task:
        namespace=task['context_view'];canonical=ROOT/'context_critics'/namespace/task['id']/'TRAINING.json';uniform=False
    else:
        namespace='full';canonical=ROOT/'token_critics'/task['id']/'TRAINING.json';uniform=False
    assert not canonical.exists()
    actual=dict(task,id='labelcache_v1_'+task['id'],_artifact_context_namespace=namespace,_uniform_context=uniform)
    result=execute(engine,actual,pool);source=ROOT/result['path'];record=read(source)
    record.update(task=task,artifact_task=actual,artifact_source=str(source.relative_to(ROOT)),artifact_source_sha256=sha(source),
        compatibility_manifest_only=True,runtime_implementation='code/r2_labelcached_critic.py',runtime_sha256=sha(ROOT/'code/r2_labelcached_critic.py'),adoption_evidence='provenance/CRITIC_LABELCACHE_EQUIVALENCE_PASS.json')
    atomic(canonical,record)
    return dict(**result,compatibility_manifest=str(canonical.relative_to(ROOT)),runtime='immutable_labelcache_v1')
