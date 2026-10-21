"""Generate complete candidates first, then use a frozen observable critic."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_eval_rollouts import Fits,load_case
    from r2_behavior_router import base_trajectory
    from r2_candidate_selector import inputs,decide
    from r2_router_runtime import transforms
    from r2_router_features import from_engine
    from r2_library_rollouts import apply,block
    from repair_score import score_group
    point=read(ROOT/task['point']);policies=[(p,read(ROOT/p['policy'])) for p in point['policies']];mode=point['mode'];assert mode in ['engineering','training','heldout']
    for spec,policy in policies:assert sha(ROOT/spec['policy'])==spec['policy_sha256']
    panel=point['panel'][task['start']:task['end']];fits=Fits();pending=[];output=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load_case,panel[0]) if panel else None
        for j,index in enumerate(panel):
            row,features,reference,_=future.result()
            if j+1<len(panel):future=reader.submit(load_case,panel[j+1])
            annotations=[];predictions=[];cache={};observations={}
            with torch.no_grad():
                hidden=engine.forward_native(features);native={};states={}
                for noise in point['seeds']:
                    native[noise],states[noise]=base_trajectory(engine,features,hidden,seed(row['token'],noise),True)
                    predictions.append(native[noise]);annotations.append(dict(arm='baseline',seed_index=noise))
                for spec,policy in policies:
                    held=policy['heldout_fold'];fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
                    assert (held<0 or fold!=held) if mode in ['training','engineering'] else held==fold
                    meta=policy['feature_meta']
                    if meta['path'] not in observations:observations[meta['path']]=from_engine(engine,transforms(meta['path'],meta['sha256'])).cpu().numpy()
                    for part in policy['parts']:
                        if part['id'] in cache:continue
                        changed,stat=apply(engine,part,fits);condition,post=engine.suffix(block(part),changed)
                        cache[part['id']]={s:engine.trajectory(features,condition,seed(row['token'],s),post) for s in point['seeds']}
                        for noise,prediction in cache[part['id']].items():
                            predictions.append(prediction);annotations.append(dict(arm='candidate_'+part['id'],seed_index=noise,relative_edit=stat['relative_edit']))
                    for noise in point['seeds']:
                        candidates=torch.stack([cache[p['id']][noise] for p in policy['parts']]).cpu().numpy()
                        x=inputs(observations[meta['path']],native[noise].cpu().numpy(),candidates,states[noise].cpu().numpy(),[p['slot'] for p in policy['parts']],policy['tier'])
                        choice,diagnostic=decide(policy,x)
                        if 'force_choice' in spec:assert mode=='engineering';choice=spec['force_choice']
                        prediction=native[noise] if choice==0 else cache[policy['parts'][choice-1]['id']][noise]
                        predictions.append(prediction);annotations.append(dict(arm=spec['id'],seed_index=noise,choice=choice,router_diagnostic=diagnostic))
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
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=output,mode=mode,seconds=time.monotonic()-began,independent_trajectories=True,selection_uses_no_true_scores=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began)
