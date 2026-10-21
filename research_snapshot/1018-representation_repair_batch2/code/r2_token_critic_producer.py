"""Full-token critic pilots, then frozen incremental training data snapshots."""
from r2_common import *
from r2_resume_support import register_once,enqueue


def main():
    setup('token_critic_producer')
    pilot=ROOT/'runs/token_critic_pilot_v1';smoke=ROOT/'runs/token_critic_engineering_v1'
    while not (pilot/'receipts/token_critic_pilot_v1.json').exists():time.sleep(15)
    trained=read(ROOT/'token_critics/token_critic_pilot_v1/TRAINING.json');checkpoint=trained['checkpoints'][-1]
    response=read(ROOT/trained['task']['responses'][0]);bank=read(ROOT/response['point']);parts={p['id']:p for p in bank['arms']}
    selected=[parts[v] for _,v in sorted(bank['policies']['PDMS'].items(),key=lambda p:int(p[0]))]
    point=smoke/'points/smoke.json'
    if not point.exists():atomic(point,dict(id='token_critic_engineering',mode='engineering',heldout_fold=-1,
        panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel'],seeds=[0,1,2],parts=selected,critics=[
            dict(id='token_critic',checkpoint=checkpoint,heldout_fold=-1,threshold=.01,risk_penalty=0.),
            dict(id='token_critic_identity',checkpoint=checkpoint,heldout_fold=-1,threshold=2.,risk_penalty=0.,force_Base=True)]))
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='token_critic_engineering',point=str(point.relative_to(ROOT)),start=0,end=2,stage=str(smoke.relative_to(ROOT)))]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='full_token_critic_independent_candidates_engineering',path=str(smoke.relative_to(ROOT)),handler='code/r2_token_critic_eval.py',handler_sha256=sha(ROOT/'code/r2_token_critic_eval.py'),kind='custom',priority=6))
    while not (smoke/'receipts/token_critic_engineering.json').exists():time.sleep(15)
    atomic(ROOT/'provenance/TOKEN_CRITIC_ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),full_valid_tokens=True,actual_generated_candidates_and_scores=True,exact_Base_available=True,PDMS_GT_not_inference_inputs=True,semantic_generalization_pending=True))
    stage=ROOT/'runs/token_critic_training_v1';handler='code/r2_token_critic.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
    if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='full_token_critics_for_observable_candidate_selection',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.18))
    protocol=ROOT/'config/TOKEN_CRITIC_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),scope='Information sufficiency control against pooled router features; independent whole-trajectory selection, not new repair experts.',
        model='two 4-head cross-attention layers, 128 channels, eight candidate trajectory queries, complete valid interface-post tokens',
        outer_folds=[-1,0,1,2,3,4],fit_seeds=[2026101801,2026101802,2026101803],
        wave1='Exactly 9 predefined seed0 systems: all three families K2/3/4, with matched S0/S1/S2 response banks.',
        wave2='All 63 independently initialized K2..8 systems and three fit seeds in the corresponding outer training fold.',
        each_wave_steps=8000,checkpoints=[4000,8000],learning_rate=.0003,calibration_session_fraction='one of seven hashed training sessions, excluded from critic updates',
        baseline_training='Training-fold natural Base labels plus actual separately generated expert candidate labels; no GT features.',
        selection_coupling='Use critic fit replicate matching expert-system replicate; never pick the best fit seed.',
        quality_GT_not_inference_inputs=True,validation_fitted=False,test_accessed=False))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue};ready=set()
    while True:
        banks={}
        for p in (ROOT/'analysis/expert_library_selection').glob('library_*.json'):
            bank=read(p);responses=[ROOT/'analysis/responses'/name/p.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if all(q.exists() for q in responses):banks[(bank['heldout_fold'],bank['system'])]=[str(q.relative_to(ROOT)) for q in responses]
        changed=False
        for held in [-1,0,1,2,3,4]:
            for wave in [1,2]:
                key=(held,wave)
                if key in ready:continue
                systems=[f'{family}_K{k}_seed{s}' for family in ['representation','response','correction'] for k in ([2,3,4] if wave==1 else range(2,9)) for s in ([0] if wave==1 else range(3))]
                if not all((held,s) in banks for s in systems):continue
                responses=sum([banks[(held,s)] for s in systems],[])
                for fit_seed in [2026101801,2026101802,2026101803]:
                    spec=dict(heldout_fold=held,wave=wave,fit_seed=fit_seed,steps=8000,checkpoints=[4000,8000],responses=responses)
                    ident='token_critic_'+digest(spec)[:24];enqueue(queue,known,dict(id=ident,**spec))
                ready.add(key);changed=True
        if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=len(ready)==12,tasks=len(queue),ready_waves=[list(k) for k in sorted(ready)],time=stamp()))
        if len(ready)==12:return
        time.sleep(60)


if __name__=='__main__':main()
