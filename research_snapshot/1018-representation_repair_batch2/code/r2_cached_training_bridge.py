"""Adopt verified cached execution for unclaimed tasks, with independent artifacts.

The queue and scientific configuration stay fixed. A compatibility manifest lets
the existing frozen producer discover the new, separately named checkpoints.
In-flight tasks complete in their original runtime; nothing is overwritten.
"""
from r2_common import *


def run(engine,task,pool):
    from r2_learned_expert_v3 import run as cached_run
    evidence=read(ROOT/'provenance/CACHED_TRAINING_AB_PASS.json')
    assert evidence['training_weights_bitwise_equal'] and evidence['case_and_seed_schedule_equal']
    assert read(ROOT/'provenance/CACHED_INTERFACE_SMOKE_PASS.json')['status']=='PASS'
    canonical=task['id'];compatibility_path=ROOT/'learned_experts'/canonical/'TRAINING.json'
    assert not compatibility_path.exists()
    actual=dict(task,id='cached_v3_'+canonical,canonical_configuration=canonical,runtime_version='cached_interface_v3')
    result=cached_run(engine,actual,pool);actual_path=ROOT/result['path'];manifest=read(actual_path)
    manifest.update(canonical_configuration=task,artifact_source=str(actual_path.relative_to(ROOT)),
                    artifact_source_sha256=sha(actual_path),runtime_implementation='code/r2_learned_expert_v3.py',
                    runtime_sha256=sha(ROOT/'code/r2_learned_expert_v3.py'),
                    adoption_evidence='provenance/CACHED_TRAINING_AB_PASS.json',compatibility_manifest_only=True)
    atomic(compatibility_path,manifest)
    return dict(**result,canonical_configuration=canonical,compatibility_manifest=str(compatibility_path.relative_to(ROOT)),
                runtime='cached_interface_v3',handler_sha256=sha(Path(__file__)))
