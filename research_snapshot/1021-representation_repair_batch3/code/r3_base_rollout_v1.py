"""Full natural train S0-S4 Base through verified immutable cached VLM states."""
from r3_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


@lru_cache(maxsize=2)
def rows_at(path,hashed):
    assert sha(path)==hashed;return read(path)


def run(engine,task,pool):
    import numpy as np
    import torch
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r2_cached_interfaces import from_cached
    from r3_runtime import prediction
    rows=rows_at(task['rows'],task['rows_sha256']);indices=list(range(task['start'],task['end']))
    timings=dict(read_decompress_seconds=0.,input_wait_seconds=0.,inference_seconds=0.,device_return_seconds=0.,scoring_wait_seconds=0.,write_seconds=0.)
    pending=[];records=[];began=time.monotonic()
    def fetch(index):
        started=time.monotonic();row=rows[index];features,_,meta=load_features(row,engine.cfg);reference=baseline_row(row)
        return row,features,meta,reference,time.monotonic()-started
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,indices[0]) if indices else None
        for offset,index in enumerate(indices):
            started=time.monotonic();row,features,meta,reference,read_seconds=future.result();timings['input_wait_seconds']+=time.monotonic()-started;timings['read_decompress_seconds']+=read_seconds
            if offset+1<len(indices):future=reader.submit(fetch,indices[offset+1])
            started=time.monotonic()
            with torch.no_grad():
                hidden=from_cached(engine,features,index)
                tensors=[prediction(engine,features,hidden,j,row['token'],capture=False)[0] for j in task['seeds']]
                timings['inference_seconds']+=time.monotonic()-started;started=time.monotonic();values=torch.stack(tensors).float().cpu().numpy();timings['device_return_seconds']+=time.monotonic()-started
            case=[]
            for j,value in zip(task['seeds'],values):
                if j==0:assert np.array_equal(value,reference['trajectory'])
                case.append(dict(token=row['token'],session=row['session'],subset=row['subset'],arm='Base',seed_index=j,seed=seed(row['token'],j),trajectory=value.tolist(),
                                 global_index=index,feature_sha256=meta['feature_sha256'],interface_export='not_yet_exported_requires_paired_replay'))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=case)),reference))
    for future,reference in pending:
        started=time.monotonic();case=future.result(timeout=1800);timings['scoring_wait_seconds']+=time.monotonic()-started
        for record in case:
            if record['seed_index']==0:assert record['score']==reference['score']
        records.extend(case)
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json');started=time.monotonic()
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=records,timing=timings,seconds=time.monotonic()-began,
                    checkpoint_sha256=engine.planner_runtime['checkpoint_sha256'],cached_native_interface=True,all_S0_trajectories_and_scores_equal_archive=True,
                    not_a_teacher_export=True))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(records),cases=len(indices),timing=timings,seconds=time.monotonic()-began)
