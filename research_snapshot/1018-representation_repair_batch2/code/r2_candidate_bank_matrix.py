"""Retain all independently generated candidate outcomes for reusable critics."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_point_response import FIELDS,metadata
    from r2_expert_space import save_npz
    point=read(ROOT/task['point']);stage=ROOT/task['stage'];rows,_=metadata();parts={}
    for config in point['policies']:
        policy=read(ROOT/config['policy']);assert policy['heldout_fold']==point['heldout_fold']
        for p in policy['parts']:parts[p['id']]=p
    ids=['baseline']+sorted(parts);aa={a:j for j,a in enumerate(ids)};panel=point['panel'];ii={rows[k]['token']:j for j,k in enumerate(panel)};seeds=point['seeds'];ss={s:j for j,s in enumerate(seeds)}
    scores=np.full((len(panel),len(ids),len(seeds),len(FIELDS)),np.nan);trajectory=np.full((len(panel),len(ids),len(seeds),8,3),np.nan,dtype=np.float32);seen=set()
    for chunk in task['chunks']:
        d=read(stage/'results'/(chunk+'.json'))
        for record in d['records']:
            if record['arm']=='baseline':arm='baseline'
            elif record['arm'].startswith('candidate_'):arm=record['arm'][len('candidate_'):]
            else:continue
            key=(ii[record['token']],aa[arm],ss[record['seed_index']]);assert key not in seen;seen.add(key)
            scores[key]=[record['score'][f] for f in FIELDS];trajectory[key]=record['trajectory']
    assert np.isfinite(scores).all() and np.isfinite(trajectory).all() and len(seen)==len(panel)*len(ids)*len(seeds)
    path=ROOT/'analysis/responses/candidate_bank_v1'/point['id'];hashed=save_npz(path.with_suffix('.npz'),global_indices=np.asarray(panel),arm_ids=np.asarray(ids),seeds=np.asarray(seeds),scores=scores,trajectory=trajectory)
    atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),matrix=str(path.with_suffix('.npz').relative_to(ROOT)),matrix_sha256=hashed,
        point=task['point'],system=point['system'],heldout_fold=point['heldout_fold'],mode=point['mode'],parts=list(parts.values()),
        cases=len(panel),seeds=seeds,arms=len(parts),fields=FIELDS,source_chunks=task['chunks'],
        actual_candidates_and_scores_reused=True,no_changed_trajectory_or_score=True,validation_accessed=False,test_accessed=False))
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),cases=len(panel),arms=len(parts))
