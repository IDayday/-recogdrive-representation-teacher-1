"""Independent complete candidates, full-token critic predictions, real rescoring."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_library_rollouts import load,apply,block
    from r2_token_critic import load as load_critic,inner_session
    from r2_cached_interfaces import from_cached
    from r2_eval_rollouts import Fits
    from repair_score import score_group
    point=read(ROOT/task['point']);mode=point['mode'];assert mode in ['engineering','calibration','heldout','training_diagnostic']
    panel=point['panel'][task['start']:task['end']];parts=point['parts'];policies=point['critics'];fits=Fits();pending=[];output=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load,panel[0],engine.cfg,True) if panel else None
        for j,index in enumerate(panel):
            row,features,reference=future.result()
            if j+1<len(panel):future=reader.submit(load,panel[j+1],engine.cfg,True)
            held=point['heldout_fold'];fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
            if mode=='heldout':assert held==fold
            else:assert held<0 or fold!=held
            if mode=='calibration':assert inner_session(row['session'])
            tensors=[];annotations=[]
            with torch.no_grad():
                hidden=from_cached(engine,features,index);h=engine.prefix['interface_post'];mask,valid=engine.mask('interface_post','valid_mean');assert valid
                context=h.reshape(-1,h.shape[-1])[mask]
                native={s:engine.trajectory(features,hidden,seed(row['token'],s)) for s in point['seeds']};candidates={s:[native[s]] for s in point['seeds']}
                for part in parts:
                    assert block(part) in ['interface_pre','interface_post']
                    changed,metrics=apply(engine,part,fits);condition,post=engine.suffix(block(part),changed)
                    for noise in point['seeds']:candidates[noise].append(engine.trajectory(features,condition,seed(row['token'],noise),post))
                for noise in point['seeds']:
                    stack=torch.stack(candidates[noise]);pred={}
                    for critic in policies:
                        model=load_critic(critic['checkpoint']['path'],critic['checkpoint']['sha256']);assert critic['heldout_fold']==held
                        pred[critic['id']]=model(context,stack).cpu().numpy()
                    values=stack.cpu().numpy()
                    for a,trajectory in enumerate(values):
                        annotation=dict(arm='baseline' if a==0 else parts[a-1]['id'],seed_index=noise,seed=seed(row['token'],noise),trajectory=trajectory.tolist(),
                            predicted_by={ident:value[a].tolist() for ident,value in pred.items()})
                        if a==0 and noise==0:assert np.array_equal(trajectory,reference['trajectory'])
                        tensors.append(annotation)
                    for critic in policies:
                        if 'threshold' not in critic:continue
                        scores=pred[critic['id']];gain=scores[1:,0]-scores[0,0];risk=np.maximum(scores[0,1:3]-scores[1:,1:3],0).sum(1)
                        utility=np.clip(gain,-1.,1.)-critic.get('risk_penalty',0.)*risk
                        choice=int(utility.argmax())+1 if utility.max()>critic['threshold'] else 0
                        if critic.get('force_Base'):choice=0
                        tensors.append(dict(arm='policy_'+critic['id'],seed_index=noise,seed=seed(row['token'],noise),choice=choice,trajectory=values[choice].tolist()))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=tensors)),row,reference))
    for future,row,reference in pending:
        records=future.result(timeout=3600);native={r['seed_index']:r for r in records if r['arm']=='baseline'}
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            if record.get('choice')==0:assert record['score']==native[record['seed_index']]['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=output,mode=mode,seconds=time.monotonic()-began,
        full_tokens_observable_only=True,candidates_not_coordinate_mixed=True,critic_does_not_access_true_outcomes=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began)
