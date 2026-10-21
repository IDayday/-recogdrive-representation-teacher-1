"""Lossless compact response matrices and exploratory per-arm repair summaries."""
from r2_common import *
from functools import lru_cache


FIELDS=['score','no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound',
        'ego_progress','comfort','driving_direction_compliance']


@lru_cache(maxsize=1)
def metadata():
    rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    return rows,{r['token']:i for i,r in enumerate(rows)}


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    stage=ROOT/task['stage'];point=read(ROOT/task['point']);rows,index=metadata()
    panel=point['panel'];arm_ids=['baseline']+[a['id'] for a in point['arms']];seeds=point['seeds']
    ii={rows[k]['token']:j for j,k in enumerate(panel)};aa={a:j for j,a in enumerate(arm_ids)};ss={s:j for j,s in enumerate(seeds)}
    scores=np.full((len(panel),len(arm_ids),len(seeds),len(FIELDS)),np.nan,dtype=np.float64)
    trajectory=np.full((len(panel),len(arm_ids),len(seeds),8,3),np.nan,dtype=np.float32)
    edits=np.full(scores.shape[:3],np.nan,dtype=np.float64);seen=set()
    action_states=np.full((len(panel),len(seeds),5,8,3),np.nan,dtype=np.float32)
    for name in task['chunks']:
        path=stage/'results'/(name+'.json');d=read(path)
        for record in d['records']:
            i=ii[record['token']];a=aa[record['arm']];s=ss[record['seed_index']];key=(i,a,s)
            assert key not in seen;seen.add(key)
            scores[i,a,s]=[record['score'][f] for f in FIELDS]
            trajectory[i,a,s]=record['trajectory'];edits[i,a,s]=record['relative_edit']
            if a==0:action_states[i,s]=record['base_action_states']
    assert len(seen)==len(panel)*len(arm_ids)*len(seeds)
    assert np.isfinite(scores).all() and np.isfinite(trajectory).all() and np.isfinite(edits).all() and np.isfinite(action_states).all()
    partitions=point.get('panel_partitions',dict(all=panel));summaries=[]
    for a,arm in enumerate(arm_ids[1:],1):
        groups={}
        for subset,selection in partitions.items():
            positions=[j for j,k in enumerate(panel) if k in selection]
            if not positions:continue
            base=scores[positions,0];after=scores[positions,a];delta=after-base
            groups[subset]=dict(cases=len(positions),sessions=len({rows[panel[j]]['session'] for j in positions}),
                    base_pdms=float(base[:,:,0].mean()*100),pdms_gain=float(delta[:,:,0].mean()*100),
                    improved=int(np.count_nonzero(delta[:,:,0]>1e-8)),damaged=int(np.count_nonzero(delta[:,:,0]< -1e-8)),
                    repaired90=int(np.count_nonzero((base[:,:,0]<.7)&(after[:,:,0]>.9))),
                    lost_high=int(np.count_nonzero((base[:,:,0]>.9)&(after[:,:,0]<=.9))),
                    net_collisions=int(np.count_nonzero(after[:,:,1]<1)-np.count_nonzero(base[:,:,1]<1)),
                    net_offroad=int(np.count_nonzero(after[:,:,2]<1)-np.count_nonzero(base[:,:,2]<1)),
                    net_zero=int(np.count_nonzero(after[:,:,0]==0)-np.count_nonzero(base[:,:,0]==0)),
                    net_TTC=int(np.count_nonzero(after[:,:,3]<1)-np.count_nonzero(base[:,:,3]<1)),
                    net_failures=int(np.count_nonzero(after[:,:,0]<.7)-np.count_nonzero(base[:,:,0]<.7)))
        summaries.append(dict(arm=arm,subsets=groups))
    folder=ROOT/'analysis/responses'/stage.name;path=folder/(point['id'] if 'id' in point else task['point_id'])
    hashed=save_npz(path.with_suffix('.npz'),global_indices=np.asarray(panel,dtype=np.int64),
                   arm_ids=np.asarray(arm_ids),seeds=np.asarray(seeds),scores=scores,trajectory=trajectory,relative_edit=edits,base_action_states=action_states)
    result=dict(status='COMPLETE',time=stamp(),task=task,point=task['point'],matrix=str(path.with_suffix('.npz').relative_to(ROOT)),
                matrix_sha256=hashed,arms=len(arm_ids)-1,cases=len(panel),seeds=seeds,fields=FIELDS,summaries=summaries,
                source_training_only=point.get('training_only',True),independent_confirmation=False,
                interpretation='Exploratory actual gains; enriched-panel means are not population performance. No significance claim.')
    atomic(path.with_suffix('.json'),result)
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),matrix=result['matrix'],arms=len(arm_ids)-1,cases=len(panel))
