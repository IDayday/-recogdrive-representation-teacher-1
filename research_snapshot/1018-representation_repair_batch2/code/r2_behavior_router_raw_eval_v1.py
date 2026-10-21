"""Real outcomes of jointly trained soft mixtures and continuous hard policies."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_library_rollouts import load
    from r2_cached_interfaces import from_cached
    from r2_behavior_router import checkpoint,current_feature,base_trajectory,coefficients
    from r2_mixed_locations_v3 import forward
    from r2_eval_rollouts import Fits
    from repair_score import score_group
    descriptor=read(ROOT/task['point']);policies=descriptor['policies'];panel=descriptor['panel'][task['start']:task['end']]
    mode=descriptor['mode'];assert mode in ['engineering','training','heldout']
    pending=[];output=[];fits=Fits();began=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load,panel[0],engine.cfg,False) if panel else None
        for j,index in enumerate(panel):
            row,features,reference=future.result()
            if j+1<len(panel):future=reader.submit(load,panel[j+1],engine.cfg,False)
            trace_required=any(p['model']['tier']=='denoising' for p in policies);annotations=[];predictions=[]
            with torch.no_grad():
                hidden=engine.forward_native(features);native={};states={}
                for noise in descriptor['seeds']:
                    native[noise],states[noise]=base_trajectory(engine,features,hidden,seed(row['token'],noise),trace_required)
                    predictions.append(native[noise]);annotations.append(dict(arm='baseline',seed_index=noise))
                features_by_tier={}
                for policy in policies:
                    model=policy['model'];held=model['heldout_fold'];assert row['subset']=='exploration'
                    fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
                    assert (held<0 or fold!=held) if mode in ['training','engineering'] else held==fold
                    module=checkpoint(policy['checkpoint']['path'],policy['checkpoint']['sha256'],model['input_dimension'],len(model['parts']))
                    for noise in descriptor['seeds']:
                        key=(held,model['tier'],noise)
                        if key not in features_by_tier:features_by_tier[key]=current_feature(engine,native[noise],states[noise],held,model['tier'])
                        logits,amount=module(features_by_tier[key]);weights,strength=coefficients(logits,amount,model['kind'])
                        strength=strength*policy.get('multiplier',1.)
                        abstain=policy.get('force_Base',False) or bool(weights[0]>=policy.get('identity_threshold',1.01))
                        if abstain or (model['kind']=='hard_continuous' and int(weights.argmax())==0):
                            prediction=native[noise];statistics=[]
                        else:
                            condition,post,stats=forward(engine,model['parts'],weights,strength,fits)
                            prediction=engine.trajectory(features,condition,seed(row['token'],noise),post)
                            statistics=torch.stack(stats).cpu().numpy().tolist()
                        predictions.append(prediction);annotations.append(dict(arm=policy['id'],seed_index=noise,
                            kind=model['kind'],identity_weight=float(weights[0]),weights=weights.cpu().numpy().tolist(),
                            strengths=strength.cpu().numpy().tolist(),abstained=abstain,statistics=statistics,
                            selected_expert=int(weights.argmax()) if model['kind']=='hard_continuous' else None))
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
            if record.get('abstained'):assert record['score']==native[record['seed_index']]['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,mode=mode,records=output,seconds=time.monotonic()-began,
        actual_joint_rollouts=True,raw_multisite_evaluation=True,deployable_information_only=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began)
