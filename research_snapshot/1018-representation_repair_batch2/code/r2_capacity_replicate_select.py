"""Training-fold own-K capacity banks; no held scores enter selection."""
from r2_common import *
from collections import defaultdict


def run(task):
    import numpy as np
    meta=read(ROOT/task['responsibility_meta']);held=task['heldout_fold'];assert meta['heldout_fold']==held
    with np.load(ROOT/meta['path']) as z:
        indices=np.array(z['global_indices']);membership=np.array(z['responsibility'])
    positions={int(i):j for j,i in enumerate(indices)};options=defaultdict(list);sources=[]
    for path in task['responses']:
        response=read(ROOT/path);assert sha(ROOT/response['matrix'])==response['matrix_sha256'];point=read(ROOT/response['point']);model=point['task']
        assert model['heldout_fold']==held and model['system']==task['parent_system']
        with np.load(ROOT/response['matrix']) as z:s=np.array(z['scores']);ii=np.array(z['global_indices']);ids=list(z['arm_ids'])
        arms={a['id']:a for a in point['arms']};base=s[:,0];slot=model['expert'];w=np.array([membership[positions[int(i)],slot] if int(i) in positions else 0. for i in ii]);assert w.sum()>0
        for j,ident in enumerate(ids[1:],1):
            arm=arms[ident];after=s[:,j];gain=float(np.sum(w[:,None]*(after[:,:,0]-base[:,:,0]))/(w.sum()*3))
            events=[int(np.sum(after[:,:,c]<1)-np.sum(base[:,:,c]<1)) for c in [1,2]]+[int(np.sum(after[:,:,0]==0)-np.sum(base[:,:,0]==0))]
            options[(model['rank'],arm['budget_factor'],slot)].append(dict(part=arm,own_weighted_gain=gain,net_events=events,safe_panel=all(v<=0 for v in events),source=path))
        sources.append(dict(path=path,sha256=sha(ROOT/path)))
    protocol=read(ROOT/task['protocol']);selections=[]
    for variant in protocol['variants']:
        arms={};policies={};selection=[]
        for role in ['PDMS','safety']:
            chosen={}
            for slot in range(3):
                values=options[(variant['rank'],variant['budget_factor'],slot)];assert len(values)==6
                safe=[v for v in values if v['safe_panel']]
                best=max(values,key=lambda v:v['own_weighted_gain']) if role=='PDMS' else max(safe,key=lambda v:v['own_weighted_gain']) if safe else min(values,key=lambda v:(sum(max(e,0) for e in v['net_events']),-v['own_weighted_gain']))
                part=best['part'];arms[part['id']]=part;chosen[str(slot)]=part['id'];selection.append(dict(role=role,expert=slot,chosen=best,all_options=values))
            policies[role]=chosen
        system=f"correction_{variant['id']}_K3_seed{task['fit_index']}";ident='capacityrep_library_'+digest(dict(system=system,held=held))[:24]
        path=ROOT/'analysis/capacity_replication_selection'/(ident+'.json');assert not path.exists()
        atomic(path,dict(status='TRAINING_ONLY_FROZEN_CAPACITY_REPLICATION_BANK',time=stamp(),system=system,heldout_fold=held,K=3,
            rank=variant['rank'],budget_factor=variant['budget_factor'],policies=policies,selection=selection,arms=list(arms.values()),
            parent_system=task['parent_system'],responsibility_meta=task['responsibility_meta'],sources=sources,protocol=task['protocol'],
            parameter_selection_only_training_fold=True,no_claim_safe_policy_from_raw_panel=True,validation_fitted=False,test_accessed=False))
        selections.append(str(path.relative_to(ROOT)))
    result=ROOT/'analysis/capacity_replication_banks'/(task['id']+'.json');atomic(result,dict(status='COMPLETE',time=stamp(),task=task,selections=selections))
    return dict(path=str(result.relative_to(ROOT)),selections=selections)
