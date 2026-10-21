"""Mechanical dependency driver for a new cache optimization; no auto cutover."""
from r2_common import *
from r2_calibrate_learners import register


def wait(path):
    while not path.exists():
        if list((RUN/'failures_gpu').glob('*.json')) or list((RUN/'failures_cpu').glob('*.json')):raise RuntimeError('Recorded experiment error; await agent review')
        time.sleep(15)


def main():
    wait(ROOT/'manifests/PATCH_COUNTS.json')
    base=ROOT/'runs/cached_interface_smoke_v3';indices=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel']
    atomic(base/'tasks.json',[dict(id='cached_interface_smoke_v3',indices=indices)]);atomic(base/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register(dict(name='cached_interface_exact_equivalence',path=str(base.relative_to(ROOT)),handler='code/r2_cached_smoke.py',handler_sha256=sha(ROOT/'code/r2_cached_smoke.py'),kind='custom',priority=6))
    wait(base/'receipts/cached_interface_smoke_v3.json')
    original=read(ROOT/'learned_experts/learned_prefetch_noise_pilot_v2/TRAINING.json')['task']
    original.update(id='learned_cached_ab_pilot_v3',handler='code/r2_learned_expert_v3.py',handler_sha256=sha(ROOT/'code/r2_learned_expert_v3.py'))
    base=ROOT/'runs/cached_training_ab_v3';atomic(base/'tasks.json',[original]);atomic(base/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register(dict(name='cached_training_exact_ab',path=str(base.relative_to(ROOT)),handler=original['handler'],handler_sha256=original['handler_sha256'],kind='custom',priority=6))
    wait(base/'receipts/learned_cached_ab_pilot_v3.json')
    h='code/r2_cached_ab_check.py';append('cpu',[dict(id='outcome_cached_training_ab_v3',handler=h,handler_sha256=sha(ROOT/h))])
    wait(ROOT/'provenance/CACHED_TRAINING_AB_PASS.json')
    print(json.dumps(dict(status='CACHE_EQUIVALENCE_PASS',evidence='provenance/CACHED_TRAINING_AB_PASS.json',automatic_cutover=False)),flush=True)


if __name__=='__main__':main()
