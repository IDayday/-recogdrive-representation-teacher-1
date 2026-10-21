"""Parallel preparation of the exact frozen causal descriptor rule, no model run."""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def data():
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    fold=np.asarray([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.asarray([r['subset']=='exploration' for r in rows])
    return rows,q,fold,explore


def run(task):
    import numpy as np
    from r2_coarse_producer import balanced
    rows,quality,fold,explore=data();first=task['fits'][0];held=first['heldout_fold'];meta_path=first['responsibility_meta'];expert=first['expert'];meta=read(ROOT/meta_path)
    with np.load(ROOT/meta['path']) as z:ii=np.array(z['global_indices']);q=np.array(z['responsibility'])
    own=q.argmax(1)==expert;salt=dict(causal_expert_quick=20261018,group=meta_path,expert=expert);f=balanced(ii[own],rows,6,salt)
    if len(f)<6:f += [int(ii[j]) for j in np.argsort(-q[:,expert]) if int(ii[j]) not in f][:6-len(f)]
    other=balanced([int(i) for i in ii[~own] if int(i) not in f],rows,2,salt);train=explore&((fold!=held) if held>=0 else True)
    h=balanced(np.flatnonzero(train&(quality>.9)),rows,2,salt);m=balanced(np.flatnonzero(train&(quality>=.7)&(quality<=.9)),rows,2,salt)
    panel=f+other+h+m;parts=dict(own=f,other=other,high=h,intermediate=m);outputs=[]
    for fit_task in task['fits']:
        assert fit_task['responsibility_meta']==meta_path and fit_task['expert']==expert
        result=read(ROOT/'analysis/delta_experts'/(fit_task['id']+'.json'));arms=[]
        for fit in result.get('fits',[]):
            for strength in [.5,1.]:
                spec=dict(kind='delta',fit=fit,strength=strength,slot=expert);arms.append(dict(id='causal_arm_'+digest(spec)[:24],**spec))
        if not arms:continue
        point=dict(id=fit_task['id'],task=fit_task,arms=arms,panel=panel,panel_partitions=parts,seeds=[0,1,2],training_only=True)
        path=ROOT/'runs/causal_expert_quick_v1/points'/(fit_task['id']+'.json')
        if path.exists():assert digest(read(path))==digest(point),'Parallel descriptor differs from frozen original rule'
        elif task.get('compare_only'):raise FileNotFoundError('Pilot must compare an existing frozen descriptor')
        else:atomic(path,point)
        outputs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),canonical_point_digest=digest(point)))
    if task.get('compare_only'):atomic(ROOT/'provenance/CAUSAL_DESCRIPTOR_PARALLEL_EQUIVALENCE.json',dict(status='PASS',time=stamp(),outputs=outputs,same_frozen_sampling_arms_and_panel=True,model_inference_not_repeated=True))
    return dict(status='COMPLETE',outputs=outputs,metadata_only=True)
