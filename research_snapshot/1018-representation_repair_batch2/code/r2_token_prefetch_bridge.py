"""Same critic training with ordered four-reader prefetch, independent artifacts."""
from r2_common import *


def run(engine,task,pool):
    from r2_token_critic_prefetch_v2 import run as execute
    proof=read(ROOT/'provenance/TOKEN_PREFETCH_AB_PASS.json');assert proof['all_arrays_bitwise_equal'] and proof['case_and_noise_schedule_equal']
    path=ROOT/'token_critics'/task['id']/'TRAINING.json';assert not path.exists()
    result=execute(engine,task,pool);source=ROOT/result['path'];manifest=read(source)
    manifest.update(artifact_source=str(source.relative_to(ROOT)),artifact_source_sha256=sha(source),compatibility_manifest_only=True,
        runtime_implementation='code/r2_token_critic_prefetch_v2.py',runtime_sha256=sha(ROOT/'code/r2_token_critic_prefetch_v2.py'),adoption_evidence='provenance/TOKEN_PREFETCH_AB_PASS.json')
    atomic(path,manifest);return dict(**result,compatibility_manifest=str(path.relative_to(ROOT)),runtime='ordered_prefetch_v2')
