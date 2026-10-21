"""Matched-data pre/post and valid/all readout variants, finite wave1 only."""
from r2_common import *
from r2_resume_support import register_once,enqueue


def main():
    while not (ROOT/'provenance/TOKEN_PREFETCH_AB_PASS.json').exists():time.sleep(15)
    smoke=ROOT/'runs/context_critic_engineering_v1';handler='code/r2_context_critic_smoke.py'
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='context_critic_engineering_v1',stage=str(smoke.relative_to(ROOT)))]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='pre_post_context_and_padding_real_engineering',path=str(smoke.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not (ROOT/'provenance/CONTEXT_CRITIC_ENGINEERING_PASS.json').exists():time.sleep(15)
    protocol=ROOT/'config/CONTEXT_CRITIC_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),views=['pre_valid','post_all','pre_all'],original_control='post_valid full-token and matched uniform-token critics',
        motivation='First held K2 has substantial real candidate oracle but weak pooled deployment selection; test loss of information at interface compression or discarded padding, without new model collection.',
        source_data='Identical predetermined nine-system wave1 response snapshots, all/5fold, all3 fit seeds. No new fitting labels or candidate resampling.',
        maximum_models=54,steps=8000,checkpoints=[4000,8000],calibration='Same excluded one-of-seven training sessions',
        selection='Same actual-quality and NC/DAC/zero calibration constraints, identity and risk/threshold grids; frozen held evaluation.',
        scope='Information/control ablation, not proof of input irreducibility. Any competitive view gets matching pooled readout and final locked natural evaluation.',validation_accessed=False,test_accessed=False))
    stage=ROOT/'runs/context_critic_training_v1';handler='code/r2_context_critic.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[]);atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='pre_post_and_all_token_critic_training',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.19,enabled=False))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue};source=ROOT/'runs/token_critic_training_v1'
    while True:
        changed=False
        if (source/'tasks.json').exists():
            for original in read(source/'tasks.json'):
                if original['wave']!=1:continue
                for view in ['pre_valid','post_all','pre_all']:
                    task=dict(original,id='context_'+view+'_'+original['id'],context_view=view)
                    if task['id'] not in known:enqueue(queue,known,task);changed=True
        if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=len(queue)==54,tasks=len(queue),time=stamp()))
        time.sleep(60)


if __name__=='__main__':main()
