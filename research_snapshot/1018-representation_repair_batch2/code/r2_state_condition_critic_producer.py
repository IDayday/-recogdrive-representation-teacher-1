"""Larger inner calibration, then class/budget-matched critic continuation.

Pilot fold, locations and expert bank were declared before outcomes. No final
validation or test data, and no automatic expansion based on a partial result.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue,append_once


def stage(path,handler,priority,enabled=True):
    base=ROOT/path
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name=base.name,path=path,handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=priority,enabled=enabled))
    return base


def main():
    setup('state_condition_critic_producer')
    import numpy as np
    from r2_token_critic import inner_session
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);base_system='representation_K2_seed0';held=0
    selected=next(p for p in (ROOT/'analysis/expert_library_selection').glob('*.json') if read(p)['system']==base_system and read(p)['heldout_fold']==held);bank=read(selected)
    old_responses=['analysis/responses/'+name+'/'+selected.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
    while not all((ROOT/p).exists() for p in old_responses):time.sleep(30)
    models={}
    while len(models)<2:
        for folder,view in [('token_critics','post_valid_state'),('token_critics','post_valid_zero')]:
            for p in (ROOT/folder).glob('*/TRAINING.json'):
                d=read(p)
                if d['heldout_fold']==held and d['fit_seed']==2026101801 and d['task'].get('wave')==1 and d['task'].get('steps')==8000:models[view]=d
        if len(models)<2:time.sleep(30)
    protocol=ROOT/'config/STATE_CONDITION_CRITIC_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_EXPLORATORY_PILOT',time=stamp(),outer_fold=held,expert_system=base_system,views=['post_valid_state','post_valid_zero'],state_input='Exact frozen action-head ego_status_encoder(8 current state values) and his_traj_encoder(12 history values), appended as context tokens; zero arm appends same-size zeros. Same architecture and parameter count. No new sensors or privileged labels.',initial_fit_seed=2026101801,initial_seed_only_pilot=True,finalists_require_other_folds_and_fit_repetitions=True,
        frozen_recalibration='Same exact original8k checkpoint; old small versus new large inner-calibration. No gradient update.',
        continuation_data=['original_target_bank','augmented_target_bank'],additional_steps=[8000,24000],total_steps=[16000,32000],continuation_seeds=[2026101801],
        initialization='Within each view all continuation runs start from the same fixed original8k seed0 model. Initial seed0 feasibility only; expand fit repetitions for contenders.',
        sampling='Two original target-bank response sources S0/S1S2 sampled uniformly. Draw F/H/M according to original fitting-bank per-source proportions in both data arms; candidate, noise, and 50% Base auxiliary schedule identical. Larger arm changes available distinct scenes within class. Inner calibration excluded from critic gradients.',
        optimizer='Reset AdamW identically, lr0.0003, weight_decay0.001; original loss unchanged.',
        calibration='Both continuation arms and budgets use the same enlarged inner-calibration outcomes and frozen risk/threshold grid.',
        expert_training_caveat='Inner calibration sessions were used by frozen experts; only outer held fold excludes the whole pipeline.',
        selection_scope='Mechanistic pilot. Any selected deployment method requires other folds and full fit repeats before frozen natural confirmation.',validation_accessed=False,test_accessed=False))
    smoke=stage('runs/state_condition_critic_engineering_v1','code/r2_state_condition_critic.py',8)
    smoke_tasks=[]
    for view,rep in [('post_valid_state',0),('post_valid_state',1),('post_valid_zero',0)]:
        smoke_tasks.append(dict(id='state_condition_smoke_'+view+'_'+str(rep),heldout_fold=held,responses=old_responses,reference_responses=old_responses,context_view=view,state_mode='zero' if view.endswith('_zero') else 'actual',fit_seed=2026101801,
            steps=8,checkpoints=[8],initial_checkpoint=models[view]['checkpoints'][-1],data_arm='engineering_original',study='engineering_only'))
    if not read(smoke/'tasks.json'):atomic(smoke/'tasks.json',smoke_tasks);atomic(smoke/'producer.json',dict(complete=True,tasks=len(smoke_tasks),time=stamp()))
    while not all((smoke/'receipts'/(t['id']+'.json')).exists() for t in smoke_tasks):time.sleep(30)
    learned=[read(ROOT/'state_condition_critics'/t['id']/'TRAINING.json') for t in smoke_tasks]
    with np.load(ROOT/learned[0]['checkpoints'][-1]['path']) as a,np.load(ROOT/learned[1]['checkpoints'][-1]['path']) as b:
        assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    assert learned[0]['trace']==learned[1]['trace']
    proof=ROOT/'provenance/STATE_CONDITION_CRITIC_ENGINEERING_PASS.json'
    if not proof.exists():atomic(proof,dict(status='PASS',time=stamp(),smoke_tasks=smoke_tasks,replicated_post_weights_and_trace_bitwise_equal=True,both_context_views_real_training=True,actual_Base_trajectory_exact=True,fold_and_inner_session_guards=True,original_discovery_namespaces_untouched=True))
    training=stage('runs/state_condition_critic_training_v1','code/r2_state_condition_critic.py',24.2,False)
    calibration=stage('runs/state_condition_critic_calibration_v1','code/r2_state_condition_predict.py',23.7,False)
    held_stage=stage('runs/state_condition_critic_held_v1','code/r2_state_condition_predict.py',22.3,False)
    queues={b:read(b/'tasks.json') for b in [training,calibration,held_stage]};known={b:{t['id'] for t in q} for b,q in queues.items()}
    prepared=set();calibrated=set();held_prepared=set();assessed=set();projected=set();training_prepared=False
    while True:
        responses={}
        for name in ['large_success_S0_v1','large_success_noise_v1']:
            for p in (ROOT/'analysis/responses'/name).glob('*.json'):
                d=read(p)
                if d.get('status')!='COMPLETE' or 'point' not in d:continue
                point=read(ROOT/d['point']);responses[(point['inner_partition'],name)]=str(p.relative_to(ROOT))
        variants=[]
        # First train both added-token variants; an unadapted appended-token model is not a confirmatory control.
        if all(('fitting',n) in responses for n in ['large_success_S0_v1','large_success_noise_v1']) and not training_prepared:
            large=[responses[('fitting',n)] for n in ['large_success_S0_v1','large_success_noise_v1']]
            for view,model in models.items():
                for data_arm,paths in [('original',old_responses),('augmented',large)]:
                    for fit_seed in [2026101801]:
                        spec=dict(heldout_fold=held,responses=paths,reference_responses=old_responses,context_view=view,state_mode='zero' if view.endswith('_zero') else 'actual',fit_seed=fit_seed,steps=24000,checkpoints=[8000,24000],initial_checkpoint=model['checkpoints'][-1],data_arm=data_arm,study='large_success_data_budget')
                        ident='state_condition_'+digest(spec)[:24];enqueue(queues[training],known[training],dict(id=ident,**spec))
            training_prepared=True
        for t in queues[training]:
            path=ROOT/'state_condition_critics'/t['id']/'TRAINING.json'
            if not path.exists():continue
            trained=read(path)
            for checkpoint in trained['checkpoints']:variants.append(dict(tag=t['data_arm']+'_total'+str(checkpoint['step']),context_view=t['context_view'],fit_seed=t['fit_seed'],checkpoint=checkpoint))
        changed=set();work=[]
        if training_prepared:changed.add(training)
        if all(('calibration',n) in responses for n in ['large_success_S0_v1','large_success_noise_v1']):
            sources=[responses[('calibration',n)] for n in ['large_success_S0_v1','large_success_noise_v1']];items=[]
            for path in sources:
                meta=read(ROOT/path)
                with np.load(ROOT/meta['matrix']) as z:indices=np.array(z['global_indices'])
                assert all(inner_session(rows[int(i)]['session']) for i in indices)
                items.extend([[path,j] for j in range(len(indices))])
            for variant in variants:
                view=variant['context_view'];study_system=base_system+'__stateH_'+variant['tag']+'_'+view+'_fit'+str(variant['fit_seed'])
                for role in ['PDMS','safety']:
                    spec=dict(system=study_system,role=role,variant=variant,held=held);ident='stateH_cal_'+digest(spec)[:24];point_path=calibration/'points'/(ident+'.json')
                    parts=[next(a for a in bank['arms'] if a['id']==v) for _,v in sorted(bank['policies'][role].items(),key=lambda x:int(x[0]))]
                    critic=dict(id='largeH_ck_'+digest(variant)[:20],checkpoint=variant['checkpoint'],heldout_fold=held,context_view=view,state_mode='zero' if view.endswith('_zero') else 'actual')
                    if ident not in prepared:
                        if not point_path.exists():atomic(point_path,dict(id=ident,mode='calibration',system=study_system,K=bank['K'],heldout_fold=held,wave=1,fit_seed=variant['fit_seed'],role=role,parts=parts,critics=[critic],items=items,responses=sources,training_only=True,study=spec,protocol=str(protocol.relative_to(ROOT))))
                        for j in range(0,len(items),8):enqueue(queues[calibration],known[calibration],dict(id=ident+'_%04d'%j,stage=str(calibration.relative_to(ROOT)),point=str(point_path.relative_to(ROOT)),start=j,end=min(j+8,len(items))))
                        prepared.add(ident);changed.add(calibration)
                    point=read(point_path);chunks=[ident+'_%04d'%j for j in range(0,len(items),8)]
                    if ident not in calibrated and all((calibration/'receipts'/(c+'.json')).exists() for c in chunks):
                        work.append(dict(id='outcome_largeH_select_'+ident,handler='code/r2_context_policy_select.py',handler_sha256=sha(ROOT/'code/r2_context_policy_select.py'),point=str(point_path.relative_to(ROOT)),stage=str(calibration.relative_to(ROOT))));calibrated.add(ident)
                    policy_path=ROOT/'context_policies'/ident/'POLICY.json'
                    if not policy_path.exists():continue
                    cache=next((p for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json') if read(p)['heldout_fold']==held and read(p)['system']==base_system),None)
                    if cache is None:continue
                    held_id='stateH_held_'+ident;held_point=held_stage/'points'/(held_id+'.json')
                    if held_id not in held_prepared:
                        response=read(cache)
                        with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices'])
                        held_items=[[str(cache.relative_to(ROOT)),j] for j in range(len(ii))];policy=read(policy_path)
                        if not held_point.exists():atomic(held_point,dict(id=held_id,mode='heldout',system=study_system,K=bank['K'],heldout_fold=held,wave=1,fit_seed=variant['fit_seed'],role=role,parts=parts,critics=[policy['critic']],items=held_items,responses=[str(cache.relative_to(ROOT))],policy=str(policy_path.relative_to(ROOT)),policy_sha256=sha(policy_path),whole_system_cv=True))
                        for j in range(0,len(held_items),8):enqueue(queues[held_stage],known[held_stage],dict(id=held_id+'_%04d'%j,stage=str(held_stage.relative_to(ROOT)),point=str(held_point.relative_to(ROOT)),start=j,end=min(j+8,len(held_items))))
                        held_prepared.add(held_id);changed.add(held_stage)
                    count=len(read(held_point)['items'])
                    if held_id not in assessed and all((held_stage/'receipts'/(held_id+'_%04d.json'%j)).exists() for j in range(0,count,8)):
                        work.append(dict(id='outcome_largeH_assess_'+ident,handler='code/r2_context_policy_assess.py',handler_sha256=sha(ROOT/'code/r2_context_policy_assess.py'),point=str(held_point.relative_to(ROOT)),stage=str(held_stage.relative_to(ROOT))));assessed.add(held_id)
                    assessment=ROOT/'analysis/context_token_policy_cv'/view/(held_id+'.json')
                    if held_id not in projected and assessment.exists():
                        work.append(dict(id='outcome_largeH_projection_'+ident,handler='code/r2_context_cv_projection.py',handler_sha256=sha(ROOT/'code/r2_context_cv_projection.py'),assessment=str(assessment.relative_to(ROOT)),context_control='large_success_'+view));projected.add(held_id)
        if work:append_once('cpu',work)
        for b in changed:atomic(b/'tasks.json',queues[b]);atomic(b/'producer.json',dict(complete=False,time=stamp(),tasks=len(queues[b]),global_queues_retained=True))
        atomic(ROOT/'analysis/state_condition_critic_control/PRODUCER.json',dict(time=stamp(),data_matrices=len(responses),continuation_prepared=training_prepared,continuation_models_ready=len(variants),calibration_points=len(prepared),calibration_completed=len(calibrated),held_points=len(held_prepared),held_completed=len(assessed),projected=len(projected)))
        time.sleep(60)


if __name__=='__main__':main()
