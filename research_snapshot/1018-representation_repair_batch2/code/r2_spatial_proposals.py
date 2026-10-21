"""Use actual multi-component responses to propose each expert's interventions."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_coarse_producer import balanced
    meta=read(ROOT/task['responsibility_meta']);held=meta['heldout_fold'];expert=task['expert']
    with np.load(ROOT/meta['path']) as z:indices=np.array(z['global_indices']);q=np.array(z['responsibility'][:,expert],dtype=np.float64)
    mapping={int(i):j for j,i in enumerate(indices)};per_area={};source_details=[]
    for item in task['responses']:
        response=read(ROOT/item['path']);point=read(ROOT/response['point']);assert point['task']['heldout_fold']==held
        with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);s=np.array(z['scores']);ids=list(z['arm_ids'])
        weight=np.asarray([q[mapping[int(i)]] if int(i) in mapping else 0. for i in ii]);assert weight.sum()>0
        base=s[:,0];arms={a['id']:a for a in point['arms']}
        for j,ident in enumerate(ids[1:],1):
            after=s[:,j];gain=float(np.sum(weight[:,None]*(after[:,:,0]-base[:,:,0]))/(weight.sum()*after.shape[1]))
            changes=[int(np.sum(after[:,:,c]<1)-np.sum(base[:,:,c]<1)) for c in [1,2]];changes.append(int(np.sum(after[:,:,0]==0)-np.sum(base[:,:,0]==0)))
            per_area.setdefault(item['area'],[]).append(dict(arm=arms[ident],own_weighted_gain=gain,net_collision=changes[0],net_offroad=changes[1],net_zero=changes[2],safe_small_panel=all(c<=0 for c in changes),source=item['path'],centered=point['task']['centered']))
        source_details.append(dict(path=item['path'],matrix_sha256=response['matrix_sha256'],area=item['area']))
    selected={};proposals=[]
    for area,options in sorted(per_area.items()):
        best=max(options,key=lambda o:o['own_weighted_gain']);safe=[o for o in options if o['safe_small_panel']]
        second=max(safe,key=lambda o:o['own_weighted_gain']) if safe else min(options,key=lambda o:(sum(max(o[k],0) for k in ['net_collision','net_offroad','net_zero']),-o['own_weighted_gain']))
        if second['arm']['id']==best['arm']['id']:
            other=[o for o in options if o['arm']['method']!=best['arm']['method'] or o['arm']['fit_path']!=best['arm']['fit_path']]
            if other:second=max(other,key=lambda o:o['own_weighted_gain'])
        for option in [best,second]:
            arm=option['arm'];part=dict(kind='analytic',arm=arm,slot=expert);ident='spatial_part_'+digest(part)[:24];selected[ident]=dict(id=ident,**part)
        proposals.append(dict(area=area,PDMS=best,conservative_or_diverse=second,actual_settings_compared=len(options)))
    assert selected
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows]);assert np.all(train[indices])
    salt=dict(spatial_refinement=20261018,group=task['responsibility_meta'],expert=expert)
    with np.load(ROOT/meta['path']) as z:dominant=np.argmax(z['responsibility'],1)==expert
    own=balanced(indices[dominant],rows,16,salt)
    if len(own)<16:own += [int(indices[j]) for j in np.argsort(-q) if int(indices[j]) not in own][:16-len(own)]
    other=balanced([int(i) for i in indices[~dominant] if int(i) not in own],rows,16,salt)
    if len(other)<16:other += balanced([int(i) for i in indices if int(i) not in own+other],rows,16-len(other),salt)
    high=balanced(np.flatnonzero(train&(quality>.9)),rows,24,salt);mid=balanced(np.flatnonzero(train&(quality>=.7)&(quality<=.9)),rows,8,salt)
    parts=dict(own=own,other=other,high=high,intermediate=mid);panel=sum(parts.values(),[]);assert len(panel)==len(set(panel))==64
    point_path=ROOT/'runs/spatial_refinement_v1/points'/(task['id']+'.json')
    point=dict(id=task['id'],task=task,arms=list(selected.values()),panel=panel,panel_partitions=parts,seeds=[0,1,2],training_only=True,
        proposal_sources=source_details,source_proposals=proposals,location_operator_strength_may_differ_by_expert=True,
        selection_scope='Small functional proposals, followed by larger actual paired outcome checks; no independent effect claim.')
    atomic(point_path,point)
    path=ROOT/'analysis/spatial_proposals'/(task['id']+'.json');atomic(path,dict(status='PROPOSED_NOT_CONFIRMED',time=stamp(),point=str(point_path.relative_to(ROOT)),task=task,areas=sorted(per_area),arms=len(selected),sources=source_details))
    return dict(path=str(path.relative_to(ROOT)),point=str(point_path.relative_to(ROOT)),arms=len(selected))
