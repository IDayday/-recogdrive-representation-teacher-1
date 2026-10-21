"""Real response libraries, reusing exact cached VLM states at interfaces.

Every candidate is generated independently with paired noise. No trajectory
coordinate mixing, GT gating or real-PDMS selection happens in this evaluator.
"""
from r2_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


@lru_cache(maxsize=1)
def rows():return read(read(ROOT/'manifests/data_source.json')['rows'])


def load(index,cfg,interfaces):
    from worker import load_features
    from vlm_core import raw_features
    from repair_engine import baseline_row
    row=rows()[index];assert row['subset']=='exploration'
    features,_,_=load_features(row,cfg) if interfaces else (raw_features(row),None,None)
    return row,features,baseline_row(row)


def block(part):
    if part['kind']=='learned':return part['training_task']['block']
    if part['kind']=='delta':return part['fit']['block']
    return part['arm']['block']


def apply(engine,part,fits):
    if part['kind']=='learned':
        from r2_learned_expert import apply as learned
        return learned(engine,part['training_task'],part['checkpoint'],part.get('strength',1.))
    if part['kind']=='delta':
        from r2_delta_regression_v2 import apply as regression
        return regression(engine,part['fit'],part.get('strength',1.))
    value,stat=engine.edited(part['arm'],fits.get(part['arm']))
    return value,dict(relative_edit=float(stat[0]/stat[1].clamp(min=1e-12)))


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_eval_rollouts import Fits
    from r2_cached_interfaces import from_cached
    from repair_score import score_group
    from r2_expert_space import save_npz
    descriptor=read(ROOT/task['point']);parts=descriptor['arms'];panel=descriptor['panel'][task['start']:task['end']]
    interfaces=all(block(p) in ['interface_pre','interface_post'] for p in parts)
    fits=Fits();pending=[];output=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load,panel[0],engine.cfg,interfaces) if panel else None
        for j,index in enumerate(panel):
            row,features,reference=future.result()
            if j+1<len(panel):future=reader.submit(load,panel[j+1],engine.cfg,interfaces)
            tensors=[];labels=[];edits=[];latent=[]
            with torch.no_grad():
                hidden=from_cached(engine,features,index) if interfaces else engine.forward_native(features)
                native={};states={}
                for s in descriptor['seeds']:
                    original=engine.agent.action_head.p_mean_variance;trace=[]
                    def traced(x,*a,**kw):trace.append(x.detach().clone());return original(x,*a,**kw)
                    engine.agent.action_head.p_mean_variance=traced
                    try:native[s]=engine.trajectory(features,hidden,seed(row['token'],s))
                    finally:engine.agent.action_head.p_mean_variance=original
                    assert len(trace)==5
                    states[s]=torch.stack(trace).squeeze(1)
                    tensors.append(native[s]);labels.append(('baseline',s));edits.append(0.)
                for part in parts:
                    changed,metrics=apply(engine,part,fits)
                    if torch.equal(changed,engine.prefix[block(part)]):predictions=native
                    else:
                        condition,post=engine.suffix(block(part),changed)
                        predictions={s:engine.trajectory(features,condition,seed(row['token'],s),post) for s in descriptor['seeds']}
                    for s,p in predictions.items():tensors.append(p);labels.append((part['id'],s));edits.append(metrics['relative_edit'])
                predictions=torch.stack(tensors).float().cpu().numpy()
                action_states=torch.stack([states[s] for s in descriptor['seeds']]).float().cpu().numpy()
            assert np.isfinite(predictions).all() and np.isfinite(action_states).all()
            records=[]
            for p,(ident,s),edit in zip(predictions,labels,edits):
                if ident=='baseline' and s==0:assert np.array_equal(p,reference['trajectory'])
                record=dict(arm=ident,seed_index=s,seed=seed(row['token'],s),trajectory=p.tolist(),relative_edit=edit)
                if ident=='baseline':record['base_action_states']=action_states[descriptor['seeds'].index(s)].tolist()
                records.append(record)
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)),row,reference))
    for future,row,reference in pending:
        records=future.result(timeout=3600)
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine();base=ROOT/task['stage'];path=base/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=output,seconds=time.monotonic()-began,
                     cached_interfaces=interfaces,independent_candidates=True,Base_latent_states_observable=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),seconds=time.monotonic()-began)
