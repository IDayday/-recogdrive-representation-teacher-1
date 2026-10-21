"""Adopt verified prefetch and publish matched-data uniform attention controls."""
from r2_common import *
from r2_resume_support import register_once,enqueue


def main():
    while not (ROOT/'provenance/TOKEN_PREFETCH_AB_PASS.json').exists():time.sleep(15)
    register_once(dict(name='verified_ordered_prefetch_full_token_training',path='runs/token_critic_training_v1',handler='code/r2_token_prefetch_bridge.py',handler_sha256=sha(ROOT/'code/r2_token_prefetch_bridge.py'),kind='custom',priority=24.17,enabled=False))
    smoke=ROOT/'runs/uniform_token_critic_smoke_v1';handler='code/r2_uniform_critic_smoke.py'
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='uniform_token_critic_smoke_v1',stage=str(smoke.relative_to(ROOT)))]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='matched_uniform_token_context_real_engineering',path=str(smoke.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=6))
    while not (ROOT/'provenance/UNIFORM_TOKEN_CRITIC_ENGINEERING_PASS.json').exists():time.sleep(15)
    stage=ROOT/'runs/uniform_token_critic_training_v1';handler='code/r2_uniform_critic_train.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
    if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='matched_data_uniform_context_critics',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.18,enabled=False))
    protocol=ROOT/'config/UNIFORM_TOKEN_CRITIC_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),source='Exact original full-token critic tasks: both data snapshots, all3 fitting seeds, all/5fold, identical8000 updates and loss.',
        change='Attention Q/K identically zero, gradient hooks zero their updates; remaining initialization/data schedule/optimizer unchanged.',
        rationale='Separate richer token readout from the advantage of a shared larger training bank; original pooled router comparison alone changes both.',
        inference='Ordinary full-token model loader, saved Q/K zero guarantees uniform token weighting. Exact same candidate/cache panels.',
        data_scope_and_compute_recorded=True,validation_accessed=False,test_accessed=False))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue};source=ROOT/'runs/token_critic_training_v1'
    while True:
        if (source/'tasks.json').exists():
            changed=False
            for original in read(source/'tasks.json'):
                task=dict(original,id='uniform_'+original['id'],parent_full_token_task=original['id'],context_control='QK_zero_uniform_mean')
                if task['id'] not in known:enqueue(queue,known,task);changed=True
            if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=False,tasks=len(queue),time=stamp()))
        time.sleep(60)


if __name__=='__main__':main()
