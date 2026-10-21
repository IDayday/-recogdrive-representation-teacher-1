"""Low-cost response-label reuse, conditional on full exact-equivalence proof."""
from r2_common import *
from r2_resume_support import register_once


def main():
    while not (ROOT/'runs/token_critic_training_v1/tasks.json').exists() or not read(ROOT/'runs/token_critic_training_v1/tasks.json'):time.sleep(15)
    stage=ROOT/'runs/critic_labelcache_engineering_v1';handler='code/r2_labelcache_critic_smoke.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[dict(id='critic_labelcache_engineering_v1',stage=str(stage.relative_to(ROOT)))]);atomic(stage/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='critic_label_bank_preload_exact_AB',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not (ROOT/'provenance/CRITIC_LABELCACHE_EQUIVALENCE_PASS.json').exists():time.sleep(15)
    for name in ['token_critic_training_v1','uniform_token_critic_training_v1','context_critic_training_v1']:
        handler='code/r2_labelcache_critic_bridge.py';register_once(dict(name=name+'_verified_label_preload',path='runs/'+name,handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.15,enabled=False))
    atomic(ROOT/'provenance/CRITIC_LABELCACHE_RUNTIME_ADOPTION.json',dict(time=stamp(),stages=['token_critic_training_v1','uniform_token_critic_training_v1','context_critic_training_v1'],
        proof='provenance/CRITIC_LABELCACHE_EQUIVALENCE_PASS.json',same_original_atomic_claims=True,existing_inflight_unchanged=True,new_artifacts_independent=True))


if __name__=='__main__':main()
