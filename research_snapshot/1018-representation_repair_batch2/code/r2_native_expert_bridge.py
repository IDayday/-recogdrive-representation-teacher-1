"""Verified immutable-Base reuse, independent artifacts, canonical discovery."""
from r2_common import *


def run(engine,task,pool):
    from r2_learned_expert_v4_nativecache import run as execute
    proof=read(ROOT/'provenance/NATIVE_TRAINING_AB_PASS.json');assert proof['all_weights_and_checkpoint_arrays_bitwise_equal'] and proof['expert_and_hard_and_soft_validated']
    assert read(ROOT/'provenance/NATIVE_CACHE_CONTRACT_PASS.json')['archive_S0_and_lru_replay_exact']
    canonical=task['id'];path=ROOT/'learned_experts'/canonical/'TRAINING.json';assert not path.exists()
    actual=dict(task,id='native_v4_'+canonical,runtime_version='verified_native_replay_v4')
    before=dict(getattr(engine,'immutable_native_counts',{}));result=execute(engine,actual,pool);source=ROOT/result['path'];manifest=read(source)
    manifest.update(task=task,artifact_task=actual,artifact_source=str(source.relative_to(ROOT)),artifact_source_sha256=sha(source),
        runtime_implementation='code/r2_learned_expert_v4_nativecache.py',runtime_sha256=sha(ROOT/'code/r2_learned_expert_v4_nativecache.py'),
        adoption_evidence='provenance/NATIVE_TRAINING_AB_PASS.json',canonical_configuration=task,compatibility_manifest_only=True,
        native_cache_before=before,native_cache_after=dict(engine.immutable_native_counts))
    atomic(path,manifest)
    return dict(**result,canonical_configuration=canonical,compatibility_manifest=str(path.relative_to(ROOT)),runtime='verified_native_replay_v4')
