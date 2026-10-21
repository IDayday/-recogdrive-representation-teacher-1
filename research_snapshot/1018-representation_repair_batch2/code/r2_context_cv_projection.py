"""Lossless canonical CV view of full-token or matched-uniform held policies."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    source=read(ROOT/task['assessment']);assert source['status']=='HELDOUT_POLICY_EVALUATED'
    assert source['heldout_outcomes_not_used_to_route'] and not source['validation_accessed'] and not source['test_accessed']
    with np.load(ROOT/source['matrix']) as z:
        index=np.array(z['global_indices']);noise=np.array(z['seeds']);base=np.array(z['base_scores']);selected=np.array(z['selected_scores']);trajectory=np.array(z['trajectory'])
    indices=sorted(set(index.tolist()));seeds=sorted(set(noise.tolist()));assert seeds==[0,1,2]
    ii={v:j for j,v in enumerate(indices)};nn={v:j for j,v in enumerate(seeds)}
    score=np.full((len(indices),2,len(seeds),base.shape[-1]),np.nan);seen=set()
    for j,(i,n) in enumerate(zip(index,noise)):
        key=(ii[int(i)],nn[int(n)]);assert key not in seen;seen.add(key);score[key[0],0,key[1]]=base[j];score[key[0],1,key[1]]=selected[j]
    assert np.isfinite(score).all() and len(seen)==len(indices)*len(seeds)
    role=source['role'];kind=task['context_control'];ident=task['id'];folder=ROOT/'analysis/responses/token_full_cv_projection_v1';path=folder/ident
    hashed=save_npz(path.with_suffix('.npz'),global_indices=np.asarray(indices),arm_ids=np.asarray(['baseline',role]),seeds=np.asarray(seeds),scores=score)
    point=ROOT/'analysis/token_cv_points'/(ident+'.json')
    atomic(point,dict(id=ident,system=source['system'],heldout_fold=source['heldout_fold'],mode='heldout',kind='wave'+str(source['wave']),panel=indices,seeds=seeds,
        original_assessment=task['assessment'],fit_seed=source['fit_seed'],role=role,lossless_statistics_view=True))
    atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),source_mode='heldout',task=dict(stage='runs/token_'+kind+'_cv_v1'),
        point=str(point.relative_to(ROOT)),matrix=str(path.with_suffix('.npz').relative_to(ROOT)),matrix_sha256=hashed,
        actual_outcomes_reused_without_reinference=True,original_assessment=task['assessment'],original_matrix_sha256=source['matrix_sha256'],
        validation_accessed=False,test_accessed=False))
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),cases=len(indices))
