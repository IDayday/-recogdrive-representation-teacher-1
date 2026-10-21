"""Heterogeneous K-expert banks by exact joins of actual paired candidate outcomes.

Each slot may select a different location, space and operator family. K is not
multiplied by the number of search sources. No trajectory or true score is made
up, interpolated or regenerated: identical rows/seeds/Base states are required.
"""
from r2_common import *
from collections import defaultdict


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows'])
    selections=[read(ROOT/s['selection']) for s in task['sources']];held=selections[0]['heldout_fold'];K=selections[0]['K']
    original=next(s for s in selections if 'parent_system' not in s);parent=original['system'];meta_path=original['arms'][0]['training_task']['responsibility_meta'];meta=read(ROOT/meta_path)
    with np.load(ROOT/meta['path']) as z:failure=np.array(z['global_indices']);membership=np.array(z['responsibility'])
    assert membership.shape[1]==K;positions={int(i):j for j,i in enumerate(failure)}
    for s in selections:assert s['heldout_fold']==held and s['K']==K and s.get('parent_system',s['system'])==parent
    matrices={};lineage=[];reference={};arms={};owners={};comparisons=defaultdict(list)
    for number,source_record in enumerate(task['sources']):
        selection=selections[number]
        for part in selection['arms']:
            if part['id'] in arms:assert digest(arms[part['id']])==digest(part)
            arms[part['id']]=part;owners.setdefault(part['id'],number)
        for noise_kind in ['S0','noise']:
            path=ROOT/source_record[noise_kind];response=read(path);point=read(ROOT/response['point']);assert point['heldout_fold']==held and point['training_only']
            assert sha(ROOT/response['matrix'])==response['matrix_sha256']
            with np.load(ROOT/response['matrix']) as z:d={k:np.array(z[k]) for k in ['global_indices','arm_ids','seeds','scores','trajectory','relative_edit','base_action_states']}
            assert all(rows[i]['subset']=='exploration' and (held<0 or int(digest(dict(session=rows[i]['session'],cv_root=20261016))[:8],16)%5!=held) for i in d['global_indices'])
            if noise_kind not in reference:reference[noise_kind]=(d,point)
            else:
                base,_=reference[noise_kind]
                for field in ['global_indices','seeds','base_action_states']:assert np.array_equal(base[field],d[field]),(noise_kind,field)
                for field in ['scores','trajectory']:assert np.array_equal(base[field][:,0],d[field][:,0]),(noise_kind,field)
            matrices[(number,noise_kind)]=d;lineage.append(dict(source=number,kind=noise_kind,path=str(path.relative_to(ROOT)),matrix_sha256=response['matrix_sha256']))
    for ident,part in arms.items():
        owner=owners[ident];slot=part['slot'];gains=[];collision=0;offroad=0;zero=0;per_seed=[]
        for noise_kind in ['S0','noise']:
            d=matrices[(owner,noise_kind)];ids=list(d['arm_ids']);a=ids.index(ident);ii=d['global_indices'];w=np.asarray([membership[positions[int(i)],slot] if int(i) in positions else 0. for i in ii]);assert w.sum()>0
            after=d['scores'][:,a];base=d['scores'][:,0]
            for n,seed_index in enumerate(d['seeds']):
                gain=float(w@(after[:,n,0]-base[:,n,0])/w.sum());gains.append(gain)
                nc=int(np.sum(after[:,n,1]<1)-np.sum(base[:,n,1]<1));dac=int(np.sum(after[:,n,2]<1)-np.sum(base[:,n,2]<1));zz=int(np.sum(after[:,n,0]==0)-np.sum(base[:,n,0]==0))
                collision+=nc;offroad+=dac;zero+=zz;per_seed.append(dict(seed=int(seed_index),own_weighted_gain=gain,net_collision=nc,net_offroad=dac,net_zero=zz))
        comparisons[slot].append(dict(part=part,source=task['sources'][owner]['name'],own_weighted_gain=float(np.mean(gains)),net_collision=collision,net_offroad=offroad,net_zero=zero,
            safe_panel=collision<=0 and offroad<=0 and zero<=0,per_seed=per_seed))
    selected={};policies={'PDMS':{},'safety':{}};details=[]
    for slot,options in sorted(comparisons.items()):
        pdms=max(options,key=lambda c:c['own_weighted_gain']);safe=[c for c in options if c['safe_panel']]
        safety=max(safe,key=lambda c:c['own_weighted_gain']) if safe else min(options,key=lambda c:(sum(max(c[k],0) for k in ['net_collision','net_offroad','net_zero']),-c['own_weighted_gain']))
        for role,value in [('PDMS',pdms),('safety',safety)]:selected[value['part']['id']]=value['part'];policies[role][str(slot)]=value['part']['id']
        details.append(dict(expert=slot,PDMS=pdms,safety=safety,safe_raw_configuration_available=bool(safe),sources_compared=sorted({o['source'] for o in options}),options=len(options)))
    variant=task['variant'];system=parent.replace('_K','_'+variant+'_K',1);path=ROOT/'analysis'/(variant+'_library_selection')/(task['id']+'.json')
    selection=dict(status='FROZEN_HETEROGENEOUS_TRAINING_PROPOSALS',time=stamp(),system=system,parent_system=parent,K=K,heldout_fold=held,formation_round=0,
        arms=list(selected.values()),policies=policies,selection=details,responsibility_meta=meta_path,source_lineage=lineage,
        own_space_operator_location_may_differ_by_slot=True,K_not_multiplied_by_sources=True,
        actual_scores_and_trajectories_reused=True,paired_Base_states_exact=True,parameter_selection_only_training_fold=True,
        no_claim_safe_policy_from_raw_panel=True,validation_fitted=False,test_accessed=False,task=task)
    atomic(path,selection)
    ordered=['baseline']+list(selected)
    for noise_kind,stage in [('S0',variant+'_library_S0_v1'),('noise',variant+'_library_noise_v1')]:
        first,point=reference[noise_kind];score=[];trajectory=[];edit=[]
        for ident in ordered:
            owner=0 if ident=='baseline' else owners[ident];d=matrices[(owner,noise_kind)];a=list(d['arm_ids']).index(ident)
            score.append(d['scores'][:,a]);trajectory.append(d['trajectory'][:,a]);edit.append(d['relative_edit'][:,a])
        output=ROOT/'analysis/responses'/stage/task['id'];hashed=save_npz(output.with_suffix('.npz'),global_indices=first['global_indices'],seeds=first['seeds'],arm_ids=np.asarray(ordered),
            scores=np.stack(score,1),trajectory=np.stack(trajectory,1),relative_edit=np.stack(edit,1),base_action_states=first['base_action_states'])
        point_path=ROOT/'runs'/stage/'points'/(task['id']+'.json');atomic(point_path,dict(id=task['id'],system=system,K=K,heldout_fold=held,arms=list(selected.values()),policies=policies,
            selection=str(path.relative_to(ROOT)),panel=point['panel'],panel_partitions=point['panel_partitions'],seeds=point['seeds'],training_only=True,
            composition='Exact column join of independently generated, already-scored immutable candidates; no coordinate mixing or synthetic outcomes.',source_lineage=lineage))
        atomic(output.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),point=str(point_path.relative_to(ROOT)),matrix=str(output.with_suffix('.npz').relative_to(ROOT)),matrix_sha256=hashed,
            cases=len(first['global_indices']),arms=len(selected),seeds=point['seeds'],fields=read(ROOT/task['sources'][0][noise_kind])['fields'],
            source_training_only=True,independent_confirmation=False,unchanged_actual_candidates_reused=True,source_lineage=lineage))
    return dict(path=str(path.relative_to(ROOT)),active_K=len(comparisons),methods=[s['name'] for s in task['sources']],GPU_reruns=0)
