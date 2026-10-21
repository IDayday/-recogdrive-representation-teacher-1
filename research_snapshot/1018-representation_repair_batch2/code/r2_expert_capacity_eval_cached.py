"""Rescore learned trajectory-trained interventions and strength checkpoints."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_cached_interfaces import from_cached
    from r2_native_cache import native as replay_native
    from r2_learned_expert import apply
    from repair_score import score_group
    descriptor=read(ROOT/task['point']);arms=descriptor['arms'];indices=descriptor['panel'][task['start']:task['end']]
    pending=[];output=[];began=time.monotonic();timing=dict(read_decode_cpu_seconds=0.,input_wait_seconds=0.,inference_submit_seconds=0.,device_return_seconds=0.,scoring_wait_seconds=0.,write_seconds=0.)
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(load_case,indices[0],engine.cfg) if indices else None
        for j,index in enumerate(indices):
            wait_started=time.monotonic();row,features,reference,read_seconds=future.result();timing['input_wait_seconds']+=time.monotonic()-wait_started;timing['read_decode_cpu_seconds']+=read_seconds
            if j+1<len(indices):future=reader.submit(load_case,indices[j+1],engine.cfg)
            tensors=[];labels=[];edits=[]
            inference_started=time.monotonic()
            with torch.no_grad():
                hidden=from_cached(engine,features,index)
                native={s:replay_native(engine,features,hidden,row,s,False)[0] for s in descriptor['seeds']}
                for s,p in native.items():tensors.append(p);labels.append(('baseline',s));edits.append(0.)
                for arm in arms:
                    changed,metrics=apply(engine,arm['training_task'],arm['checkpoint'],arm['strength'])
                    if torch.equal(changed,engine.prefix[arm['training_task']['block']]):predictions=native
                    else:
                        condition,interface=engine.suffix(arm['training_task']['block'],changed)
                        predictions={s:engine.trajectory(features,condition,seed(row['token'],s),interface) for s in descriptor['seeds']}
                    for s,p in predictions.items():tensors.append(p);labels.append((arm['id'],s));edits.append(metrics['relative_edit'])
                timing['inference_submit_seconds']+=time.monotonic()-inference_started;return_started=time.monotonic();predictions=torch.stack(tensors).float().cpu().numpy();timing['device_return_seconds']+=time.monotonic()-return_started
            records=[]
            for p,(name,s),edit in zip(predictions,labels,edits):
                if name=='baseline' and s==0:assert np.array_equal(p,reference['trajectory'])
                records.append(dict(arm=name,seed_index=s,seed=seed(row['token'],s),trajectory=p.tolist(),relative_edit=edit))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)),row,reference))
    for future,row,reference in pending:
        started=time.monotonic();records=future.result(timeout=3600);timing['scoring_wait_seconds']+=time.monotonic()-started
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine();base=ROOT/task['stage'];path=base/'results'/(task['id']+'.json')
    started=time.monotonic()
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=output,seconds=time.monotonic()-began,
                     real_rescoring=True,hidden_mse_training=False,cached_interface=True,native_replay=True,timing_before_write=timing))
    timing['write_seconds']=time.monotonic()-started
    atomic(path.with_suffix('.timing.json'),dict(time=stamp(),timing=timing,seconds=time.monotonic()-began))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(output),timing=timing,seconds=time.monotonic()-began)


def load_case(index,cfg):
    from r2_eval_rollouts import rows
    from worker import load_features
    from repair_engine import baseline_row
    began=time.monotonic();row=rows()[index];assert row['subset']=='exploration';features,_,_=load_features(row,cfg)
    return row,features,baseline_row(row),time.monotonic()-began
