"""Verify reused outcomes and full-token predictions against fresh actual rollouts."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    from r2_token_predict import run as predict
    from r2_token_critic_eval import run as regenerate
    from r2_point_response import FIELDS
    result=predict(engine,task,pool);point=read(ROOT/task['point']);replay=read(ROOT/task['replay_point'])
    other=dict(task,id=task['id']+'_fresh',point=task['replay_point'],start=0,end=len(replay['panel']))
    generated=regenerate(engine,other,pool);fresh=read(ROOT/generated['path'])
    with np.load(ROOT/result['matrix']) as z:
        indices=np.array(z['global_indices']);seeds=np.array(z['seeds']);ids=list(z['arm_ids']);scores=np.array(z['scores']);trajectories=np.array(z['trajectory']);predicted=np.array(z['predicted'])
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);lookup={(rows[i]['token'],int(s)):j for j,(i,s) in enumerate(zip(indices,seeds))};maximum=0.;checked=0
    for record in fresh['records']:
        if record['arm'] not in ids:continue
        j=lookup[(record['token'],record['seed_index'])];a=ids.index(record['arm'])
        assert np.array_equal(trajectories[j,a],np.asarray(record['trajectory'],dtype=np.float32))
        assert np.array_equal(scores[j,a],np.asarray([record['score'][f] for f in FIELDS],dtype=np.float64))
        actual=np.asarray(record['predicted_by'][point['critics'][0]['id']]);error=float(np.max(np.abs(actual-predicted[j,0,a])))
        assert error<1e-6;maximum=max(maximum,error);checked+=1
    assert checked==scores.shape[0]*scores.shape[1]
    path=ROOT/'provenance/TOKEN_PREDICTION_REUSE_SMOKE_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),candidates_checked=checked,trajectories_bitwise_equal=True,actual_scores_exact=True,
        maximum_prediction_difference=maximum,full_token_prediction_matches_fresh_generation=True,
        reuse_point=task['point'],fresh_point=task['replay_point'],source_handler='code/r2_token_predict.py'))
    return dict(path=str(path.relative_to(ROOT)),checked=checked,maximum_prediction_difference=maximum)
