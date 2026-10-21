"""Choose each refitted expert's configuration using only its training responses."""
from r2_common import *
from collections import defaultdict


def run(task):
    import numpy as np
    meta=read(ROOT/task['responsibility_meta']);held=meta['heldout_fold']
    with np.load(ROOT/meta['path']) as z:indices=np.array(z['global_indices']);responsibility=np.array(z['responsibility'])
    positions={int(i):j for j,i in enumerate(indices)};candidates=defaultdict(list);reference=None;sample=None
    for path in task['responses']:
        response=read(ROOT/path);point=read(ROOT/response['point']);arms={a['id']:a for a in point['arms']}
        with np.load(ROOT/response['matrix']) as z:scores=np.array(z['scores']);ii=np.array(z['global_indices']);ids=list(z['arm_ids'])
        if reference is None:reference=scores[:,0];sample=ii
        else:assert np.array_equal(reference,scores[:,0]) and np.array_equal(sample,ii)
        for j,ident in enumerate(ids[1:],1):
            part=arms[ident];slot=part['slot'];weights=np.asarray([responsibility[positions[int(i)],slot] if int(i) in positions else 0. for i in ii])
            assert weights.sum()>0;after=scores[:,j];delta=after-reference
            gain=float(np.sum(weights[:,None]*delta[:,:,0])/(weights.sum()*delta.shape[1]));collision=int(np.count_nonzero(after[:,:,1]<1)-np.count_nonzero(reference[:,:,1]<1));offroad=int(np.count_nonzero(after[:,:,2]<1)-np.count_nonzero(reference[:,:,2]<1));zero=int(np.count_nonzero(after[:,:,0]==0)-np.count_nonzero(reference[:,:,0]==0))
            candidates[slot].append(dict(part=part,own_weighted_gain=gain,net_collision=collision,net_offroad=offroad,net_zero=zero,safe_panel=collision<=0 and offroad<=0 and zero<=0,source=path))
    policies={'PDMS':{},'safety':{}};arms={};selection=[]
    for slot,options in sorted(candidates.items()):
        pdms=max(options,key=lambda x:x['own_weighted_gain']);safe=[v for v in options if v['safe_panel']]
        safety=max(safe,key=lambda x:x['own_weighted_gain']) if safe else min(options,key=lambda x:(sum(max(x[k],0) for k in ['net_collision','net_offroad','net_zero']),-x['own_weighted_gain']))
        for role,value in [('PDMS',pdms),('safety',safety)]:part=value['part'];arms[part['id']]=part;policies[role][str(slot)]=part['id']
        selection.append(dict(expert=slot,PDMS=pdms,safety=safety,safe_raw_configuration_available=bool(safe),search_candidates=len(options)))
    path=ROOT/'analysis/variant_library_selection'/(task['id']+'.json')
    result=dict(status='FROZEN_TRAINING_PROPOSALS',time=stamp(),system=task['system'],parent_system=meta['parent_system'],formation_round=1,
        K=meta['K'],heldout_fold=held,arms=list(arms.values()),policies=policies,selection=selection,responsibility_meta=task['responsibility_meta'],
        parameter_selection_only_training_fold=True,no_claim_safe_policy_from_raw_panel=True,actual_full_feedback_pending=True,
        validation_fitted=False,test_accessed=False,task=task)
    atomic(path,result);return dict(path=str(path.relative_to(ROOT)),active_K=len(candidates),proposals=len(arms))
