"""Fresh natural-population rollouts for an explicitly frozen policy pack.

This program is prepared before finalist selection. Formal invocation requires
an exact candidate/row-manifest lock. No GT, true PDMS or failure label enters
any deployment decision. All expert candidates are whole trajectories; soft
policies are actual hidden interventions through the network.
"""
from r2_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


@lru_cache(maxsize=8)
def manifest(path,expected):
    assert sha(ROOT/path)==expected
    return read(ROOT/path)


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r2_eval_rollouts import Fits
    from r2_library_rollouts import apply,block
    from r2_behavior_router import base_trajectory,current_feature,checkpoint,coefficients
    from r2_mixed_locations_v3 import forward as mixture
    from r2_router_runtime import feature,decide,transforms
    from r2_router_features import from_engine
    from r2_candidate_selector import inputs,decide as candidate_decide
    from r2_context_critic import load as critic_load
    from r2_token_policy_select import choices
    lock=manifest(task['lock'],task['lock_sha256']);pack=manifest(task['pack'],task['pack_sha256'])
    assert lock['pack_sha256']==task['pack_sha256'] and lock['rows_sha256']==task['rows_sha256']
    mode=task['mode'];assert mode in ['engineering','validation','test'] and mode in lock['authorized_modes']
    assert mode=='engineering' or lock['status']=='FROZEN_BEFORE_CONFIRMATION'
    if mode=='test':assert lock['final_test_selection_frozen'] and task['seeds']==[0,1,2,3,4]
    rows=manifest(task['rows'],task['rows_sha256']);panel=task['panel'][task['start']:task['end']]
    policies=[];parts={}
    assert len({p['id'] for p in pack['policies']})==len(pack['policies'])
    for config in pack['policies']:
        assert config['kind'] in ['hard','candidate','joint','token','finite','Base']
        if config['kind']=='Base':policies.append((config,None));continue
        policy=manifest(config['policy'],config['policy_sha256']);assert policy['heldout_fold']==-1
        own=policy['configuration']['model']['parts'] if config['kind'] in ['joint','finite'] else policy['parts']
        for part in own:
            if part['id'] in parts:assert digest(parts[part['id']])==digest(part)
            parts[part['id']]=part
        policies.append((config,policy))
    fits=Fits();pending=[];output=[];began=time.monotonic();timing=dict(input_wait_seconds=0.,inference_seconds=0.,device_return_seconds=0.,scoring_wait_seconds=0.)

    def fetch(index):
        row=rows[index]
        assert row['subset']==('exploration' if mode=='engineering' else mode)
        features=raw_features(row)
        if task.get('reference_mode')=='navtrain_archive':
            assert mode!='test';reference=baseline_row(row)
        elif row.get('reference_file'):
            data=read(row['reference_file']);reference=next(r for r in data['records'] if r['token']==row['token'])
        else:reference=None
        metric_sha=reference['metric_sha256'] if reference is not None else row.get('metric_sha256') or sha(row['metric_cache'])
        return row,features,reference,metric_sha

    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,panel[0]) if panel else None
        for j,index in enumerate(panel):
            started=time.monotonic();row,features,reference,metric_sha=future.result();timing['input_wait_seconds']+=time.monotonic()-started
            if j+1<len(panel):future=reader.submit(fetch,panel[j+1])
            tensors=[];annotations=[];started=time.monotonic()
            with torch.no_grad():
                hidden=engine.forward_native(features);native={};states={};candidate={};contexts={};observations={}
                for noise in task['seeds']:
                    native[noise],states[noise]=base_trajectory(engine,features,hidden,seed(row['token'],noise),True)
                    tensors.append(native[noise]);annotations.append(dict(arm='baseline',seed_index=noise,choice=0,native_equal=True))
                def independent(part):
                    if part['id'] not in candidate:
                        value,stat=apply(engine,part,fits);site=block(part)
                        if torch.equal(value,engine.prefix[site]):predictions=native
                        else:
                            condition,post=engine.suffix(site,value);predictions={n:engine.trajectory(features,condition,seed(row['token'],n),post) for n in task['seeds']}
                        candidate[part['id']]=predictions
                        if pack.get('include_raw_experts',True):
                            for n in task['seeds']:
                                tensors.append(predictions[n]);annotations.append(dict(arm='candidate_'+part['id'],seed_index=n,relative_edit=stat['relative_edit'],native_equal=torch.equal(predictions[n],native[n])))
                    return candidate[part['id']]
                if pack.get('include_raw_experts',True):
                    for part in parts.values():independent(part)
                for config,policy in policies:
                    kind=config['kind']
                    if kind in ['candidate','token']:
                        for part in policy['parts']:independent(part)
                    for noise in task['seeds']:
                        diagnostic={};choice=None;statistics=[]
                        if kind=='Base':prediction=native[noise];choice=0
                        elif kind=='hard':
                            x=feature(engine,native[noise].cpu().numpy(),states[noise].cpu().numpy(),policy);choice,diagnostic=decide(policy,x)
                            prediction=native[noise] if choice==0 else independent(policy['parts'][choice-1])[noise]
                        elif kind=='candidate':
                            meta=policy['feature_meta']
                            if meta['path'] not in observations:observations[meta['path']]=from_engine(engine,transforms(meta['path'],meta['sha256'])).cpu().numpy()
                            actual=torch.stack([candidate[p['id']][noise] for p in policy['parts']]).cpu().numpy()
                            x=inputs(observations[meta['path']],native[noise].cpu().numpy(),actual,states[noise].cpu().numpy(),[p['slot'] for p in policy['parts']],policy['tier'])
                            choice,diagnostic=candidate_decide(policy,x);prediction=native[noise] if choice==0 else candidate[policy['parts'][choice-1]['id']][noise]
                        elif kind=='finite':
                            setting=policy['configuration'];model=setting['model'];assert model['heldout_fold']==-1 and model['tier'] in ['observation','trajectory']
                            module=checkpoint(setting['checkpoint']['path'],setting['checkpoint']['sha256'],model['input_dimension'],len(model['parts']))
                            logits,amount=module(current_feature(engine,native[noise],None,-1,model['tier']));assert torch.equal(amount,torch.ones_like(amount));choice=int(logits.argmax())
                            if 'force_choice' in config:assert mode=='engineering';choice=int(config['force_choice'])
                            assert 0<=choice<=len(model['parts']);prediction=native[noise] if choice==0 else independent(model['parts'][choice-1])[noise]
                            diagnostic=dict(actual_outcome_router=True,logits=logits.cpu().numpy().tolist(),fixed_strength=1.)
                        elif kind=='token':
                            critic=policy['critic'];assert critic['heldout_fold']==-1;view=critic.get('context_view','post_valid')
                            if view not in contexts:
                                site='interface_pre' if view.startswith('pre') else 'interface_post';group='all_mean' if view.endswith('all') else 'valid_mean'
                                h=engine.prefix[site];mask,valid=engine.mask(site,group);assert valid;contexts[view]=h.reshape(-1,h.shape[-1])[mask]
                            actual=torch.stack([native[noise]]+[candidate[p['id']][noise] for p in policy['parts']]);model=critic_load(critic['checkpoint']['path'],critic['checkpoint']['sha256'])
                            predicted=model(contexts[view],actual).cpu().numpy();choice=int(choices(predicted[None],critic['risk_penalty'],critic['threshold'])[0]);prediction=actual[choice]
                            diagnostic=dict(context_view=view,predicted=predicted.tolist())
                        else:
                            setting=policy['configuration'];model=setting['model'];assert model['heldout_fold']==-1;module=checkpoint(setting['checkpoint']['path'],setting['checkpoint']['sha256'],model['input_dimension'],len(model['parts']))
                            x=current_feature(engine,native[noise],states[noise],-1,model['tier']);logits,amount=module(x);weights,strength=coefficients(logits,amount,model['kind']);strength=strength*setting.get('multiplier',1.)
                            abstain=setting.get('force_Base',False) or bool(weights[0]>=setting.get('identity_threshold',1.01)) or (model['kind']=='hard_continuous' and int(weights.argmax())==0)
                            if abstain:prediction=native[noise];choice=0
                            else:
                                condition,post,stats=mixture(engine,model['parts'],weights,strength,fits);prediction=engine.trajectory(features,condition,seed(row['token'],noise),post);statistics=torch.stack(stats).cpu().numpy().tolist()
                            diagnostic=dict(weights=weights.cpu().numpy().tolist(),strengths=strength.cpu().numpy().tolist(),abstained=abstain)
                        tensors.append(prediction);annotations.append(dict(arm=config['id'],seed_index=noise,kind=kind,choice=choice,native_equal=torch.equal(prediction,native[noise]),statistics=statistics,router_diagnostic=diagnostic))
                resampling_K=pack.get('base_resampling_extra_candidates',0);assert isinstance(resampling_K,int) and 0<=resampling_K<=8
                for primary in task['seeds']:
                    for draw in range(resampling_K):
                        noise_index=5+primary*resampling_K+draw
                        extra=engine.trajectory(features,hidden,seed(row['token'],noise_index))
                        tensors.append(extra);annotations.append(dict(arm='base_resample_'+str(draw+1),seed_index=primary,noise_draw_index=noise_index,native_equal=torch.equal(extra,native[primary]),matched_opportunity_control=True))
                timing['inference_seconds']+=time.monotonic()-started;started=time.monotonic();values=torch.stack(tensors).float().cpu().numpy();timing['device_return_seconds']+=time.monotonic()-started
            records=[]
            for value,annotation in zip(values,annotations):
                if reference is not None and annotation['arm']=='baseline' and annotation['seed_index']==0:assert np.array_equal(value,reference['trajectory'])
                records.append(dict(**annotation,trajectory=value.tolist(),seed=seed(row['token'],annotation.get('noise_draw_index',annotation['seed_index']))))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=metric_sha,scoring=engine.cfg['scoring'],records=records)),row,reference))
    for future,row,reference in pending:
        started=time.monotonic();records=future.result(timeout=3600);timing['scoring_wait_seconds']+=time.monotonic()-started;native={r['seed_index']:r for r in records if r['arm']=='baseline'}
        for record in records:
            if reference is not None and record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            if record['native_equal']:assert record['trajectory']==native[record['seed_index']]['trajectory'] and record['score']==native[record['seed_index']]['score']
            record.update(token=row['token'],session=row['session'],subset=row['subset'],original_S0_quality=row.get('quality','unlabelled_before_confirmation'))
        output.extend(records)
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,mode=mode,records=output,timing=timing,seconds=time.monotonic()-began,
        actual_fresh_generation_and_independent_scoring=True,policy_pack_frozen=True,no_true_score_or_GT_routing=True,base_weights_frozen=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began,timing=timing)
