"""Lossless policy response matrices; finite, unique, complete paired coverage."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    from r2_point_response import FIELDS,metadata
    point=read(ROOT/task['point']);stage=ROOT/task['stage'];rows,index=metadata();panel=point['panel'];seeds=point['seeds']
    arm_ids=['baseline']+[p['id'] for p in point['policies']];aa={a:j for j,a in enumerate(arm_ids)};ii={rows[k]['token']:j for j,k in enumerate(panel)};ss={s:j for j,s in enumerate(seeds)}
    shape=(len(panel),len(arm_ids),len(seeds));scores=np.full((*shape,len(FIELDS)),np.nan,dtype=np.float64);trajectory=np.full((*shape,8,3),np.nan,dtype=np.float32)
    edit=np.full(shape,np.nan);seen=set()
    for ident in task['chunks']:
        d=read(stage/'results'/(ident+'.json'))
        for record in d['records']:
            if record['arm'] not in aa:continue
            i=ii[record['token']];a=aa[record['arm']];s=ss[record['seed_index']];key=(i,a,s);assert key not in seen;seen.add(key)
            scores[i,a,s]=[record['score'][f] for f in FIELDS];trajectory[i,a,s]=record['trajectory']
            edit[i,a,s]=record.get('relative_edit',max([v[0]/max(v[1],1e-12) for v in record.get('statistics',[])]+[0.]))
    assert len(seen)==int(np.prod(shape)) and np.isfinite(scores).all() and np.isfinite(trajectory).all() and np.isfinite(edit).all()
    folder=ROOT/'analysis/responses'/stage.name;path=folder/point['id'];hashed=save_npz(path.with_suffix('.npz'),global_indices=np.asarray(panel),arm_ids=np.asarray(arm_ids),seeds=np.asarray(seeds),scores=scores,trajectory=trajectory,relative_edit=edit)
    atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),task=task,point=task['point'],matrix=str(path.with_suffix('.npz').relative_to(ROOT)),matrix_sha256=hashed,
        cases=len(panel),arms=len(arm_ids)-1,seeds=seeds,fields=FIELDS,source_mode=point['mode'],
        independent_confirmation=point['mode']=='heldout',validation_accessed=False,test_accessed=False))
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),cases=len(panel),arms=len(arm_ids)-1)
