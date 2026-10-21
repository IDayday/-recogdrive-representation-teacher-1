"""True policy rollouts: held-fold guard, paired seeds, observable-only routing."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_eval_rollouts import Fits,load_case
    from r2_router_runtime import feature,decide
    from r2_library_rollouts import apply,block
    from repair_score import score_group
    descriptor=read(ROOT/task['point']);mode=descriptor['mode'];assert mode in ['engineering','training','heldout']
    policies=[]
    for p in descriptor['policies']:
        if 'policy_sha256' in p:assert sha(ROOT/p['policy'])==p['policy_sha256']
        policies.append((p,read(ROOT/p['policy'])))
    panel=descriptor['panel'][task['start']:task['end']];fits=Fits();pending=[];output=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load_case,panel[0]) if panel else None
        for j,index in enumerate(panel):
            row,features,reference,_=future.result()
            if j+1<len(panel):future=reader.submit(load_case,panel[j+1])
            for config,policy in policies:
                held=policy['heldout_fold'];fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
                if mode=='training':assert held<0 or fold!=held
                if mode=='heldout':assert held>=0 and fold==held
                if 'force_choice' in config:assert mode=='engineering'
            predictions=[];annotations=[]
            with torch.no_grad():
                hidden=engine.forward_native(features)
                native={};state={}
                for noise in descriptor['seeds']:
                    original=engine.agent.action_head.p_mean_variance;trace=[]
                    def traced(x,*a,**kw):trace.append(x.detach().clone());return original(x,*a,**kw)
                    engine.agent.action_head.p_mean_variance=traced
                    try:native[noise]=engine.trajectory(features,hidden,seed(row['token'],noise))
                    finally:engine.agent.action_head.p_mean_variance=original
                    assert len(trace)==5;state[noise]=torch.stack(trace).squeeze(1).float().cpu().numpy()
                    predictions.append(native[noise]);annotations.append(dict(arm='baseline',seed_index=noise,choice=0,relative_edit=0.,global_relative_edit=0.))
                for config,policy in policies:
                    for noise in descriptor['seeds']:
                        base=native[noise].cpu().numpy();observed=feature(engine,base,state[noise],policy)
                        choice,diagnostic=decide(policy,observed)
                        if mode=='engineering':
                            from r2_router_fit import context
                            cached,_=context(policy['heldout_fold']);difference=float(np.max(np.abs(observed[:192]-cached[index])))
                            assert difference<.005,('Runtime/cache router feature mismatch',difference)
                            diagnostic['runtime_cache_observation_max_abs']=difference
                        if 'force_choice' in config:choice=int(config['force_choice'])
                        if choice==0:prediction=native[noise];relative=0.;global_relative=0.
                        else:
                            part=policy['parts'][choice-1];changed,metrics=apply(engine,part,fits);location=block(part)
                            global_relative=float((changed.float()-engine.prefix[location].float()).norm()/engine.prefix[location].float().norm().clamp(min=1e-12))
                            relative=metrics['relative_edit'];condition,post=engine.suffix(location,changed)
                            prediction=engine.trajectory(features,condition,seed(row['token'],noise),post)
                        predictions.append(prediction);annotations.append(dict(arm=config['id'],seed_index=noise,choice=choice,
                            relative_edit=relative,global_relative_edit=global_relative,router_diagnostic=diagnostic,
                            nominal_K=policy['nominal_K'],active_K=policy['active_K'],information_tier=policy['tier']))
                values=torch.stack(predictions).float().cpu().numpy()
            records=[]
            for trajectory,annotation in zip(values,annotations):
                if annotation['arm']=='baseline' and annotation['seed_index']==0:assert np.array_equal(trajectory,reference['trajectory'])
                records.append(dict(**annotation,trajectory=trajectory.tolist(),seed=seed(row['token'],annotation['seed_index'])))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)),row,reference))
    for future,row,reference in pending:
        records=future.result(timeout=3600);native={r['seed_index']:r for r in records if r['arm']=='baseline'}
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            if record.get('choice')==0:assert record['score']==native[record['seed_index']]['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,mode=mode,records=output,seconds=time.monotonic()-began,
                     learned_router_uses_quality_or_GT=False,paired_native_sampler=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began)
