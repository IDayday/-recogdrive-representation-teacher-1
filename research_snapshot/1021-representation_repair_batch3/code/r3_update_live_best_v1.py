"""Incremental three-endpoint union of fully audited formed packs and first42.

Analysis revisions are retained. No teacher snapshot is extracted or frozen;
the original first42 distillation teacher is never modified. R3 compares only
S0-S2, then retains the actual S3/S4 result even when it deteriorates.
"""
from r3_common import *
import argparse
import fcntl


def endpoint_arrays(scores,trajectories,choice):
    import numpy as np
    n=len(choice);ix=np.arange(n)
    q=np.stack([np.stack([scores[ix,choice[:,j],j] for j in range(5)],axis=1),scores[ix,choice[:,5]],scores[ix,choice[:,6]]],axis=1)
    t=np.stack([np.stack([trajectories[ix,choice[:,j],j] for j in range(5)],axis=1),trajectories[ix,choice[:,5]],trajectories[ix,choice[:,6]]],axis=1)
    return q,t


def merge(quality,trajectory,choice,edits,catalog,new_quality,new_trajectory,new_choice,new_edits,new_catalog):
    import numpy as np
    old_ids=[c['id'] for c in catalog];new_ids=[c['id'] for c in new_catalog]
    assert old_ids[0]==new_ids[0]=='Base' and len(old_ids)==len(set(old_ids)) and len(new_ids)==len(set(new_ids))
    lookup={ident:i for i,ident in enumerate(old_ids)};remap=[]
    for item in new_catalog:
        ident=item['id']
        if ident in lookup:assert ident=='Base' or catalog[lookup[ident]]==item, 'Candidate ID collision requires source review'
        else:lookup[ident]=len(catalog);catalog.append(item)
        remap.append(lookup[ident])
    incoming=np.asarray(remap,dtype=np.int64)[new_choice];names=np.asarray([c['id'] for c in catalog]);counts={}
    def prefer(value,previous,amount,old_amount,new_id,old_id):
        tie=(value==previous)
        tie_better=((new_id==0)&(old_id!=0))|((new_id!=0)&(old_id!=0)&((amount<old_amount)|((amount==old_amount)&(names[new_id]<names[old_id]))))
        return (value>previous)|(tie&tie_better)
    for j in range(5):
        mask=prefer(new_quality[:,0,j,0],quality[:,0,j,0],new_edits[:,j],edits[:,j],incoming[:,j],choice[:,j])
        quality[mask,0,j]=new_quality[mask,0,j];trajectory[mask,0,j]=new_trajectory[mask,0,j];choice[mask,j]=incoming[mask,j];edits[mask,j]=new_edits[mask,j]
        counts['R1_S'+str(j)]=int(mask.sum())
    for endpoint,column,noises,name in [(1,5,list(range(5)),'R2'),(2,6,list(range(3)),'R3')]:
        # Contiguous rows preserve the same five/three-value mean convention as
        # the original generic selector; no rounding or tolerance changes ties.
        value=np.ascontiguousarray(new_quality[:,endpoint,noises,0]).mean(1)
        previous=np.ascontiguousarray(quality[:,endpoint,noises,0]).mean(1)
        mask=prefer(value,previous,new_edits[:,column],edits[:,column],incoming[:,column],choice[:,column])
        quality[mask,endpoint]=new_quality[mask,endpoint];trajectory[mask,endpoint]=new_trajectory[mask,endpoint]
        choice[mask,column]=incoming[mask,column];edits[mask,column]=new_edits[mask,column];counts[name]=int(mask.sum())
    return counts


def statistics(quality,baseline,rows,positions):
    import numpy as np
    from r3_finish42_v1 import summarize
    # The synthetic axis is only an adapter for endpoint statistics. It is not
    # an expert pool: in particular, mixed R1 cannot be a fixed R3 candidate.
    q=np.concatenate([baseline[:,None],quality],axis=1)
    selected=np.tile(np.asarray([1,1,1,1,1,2,3],dtype=np.int64),(len(q),1))
    result=summarize(q,selected,rows,positions)
    use=np.asarray(positions,dtype=np.int64)
    result['R3_first_three_unresolved']=int(((quality[use,0,:3,0]<.9).any(1)|(quality[use,2,:3,0].mean(1)<.9)).sum())
    result['already_selected_endpoints_not_a_synthetic_candidate_library']=True
    return result


def main(a):
    setup('live_union/'+a.cohort,threads=4)
    import numpy as np
    source=ROOT/'analysis'/('first42_'+a.cohort+'_v1')/'SUMMARY.json';first=read(source)
    count=103288 if a.cohort=='navtrain' else 12146
    assert first['status']=='PASS_COMPLETE_AUDITED_FIRST42' and first['cases']==count
    rows=read(first['rows']);assert len(rows)==count and sha(first['rows'])==first['rows_sha256']
    first_pack=ROOT/'manifests/first42_v1.json';ids=[e['id'] for e in read(first_pack)['entries']]
    base_scores=np.load(ROOT/first['artifacts']['scores.npy']['path'],mmap_mode='r',allow_pickle=False)
    baseline=np.asarray(base_scores[:,0]);base_trajectory=np.load(ROOT/first['artifacts']['trajectories.npy']['path'],mmap_mode='r',allow_pickle=False)
    folder=ROOT/'analysis/live_best_v1'/a.cohort;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'UPDATE.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);pointer=folder/'LIVE.json';old_pointer=read(pointer) if pointer.exists() else None
        if old_pointer:
            previous=ROOT/old_pointer['summary'];assert sha(previous)==old_pointer['summary_sha256'];old=read(previous)
            assert old['status']=='PASS_AUDITED_LIBRARY_LIVE_BEST' and old['cohort']==a.cohort and old['cases']==count
            for value in old['artifacts'].values():assert sha(ROOT/value['path'])==value['sha256']
            def load(name):return np.load(ROOT/old['artifacts'][name]['path'],allow_pickle=False)
            quality=load('quality.npy');trajectory=load('trajectories.npy');choice=load('choice.npy');edits=load('selected_edits.npy')
            catalog=read(ROOT/old['artifacts']['CATALOG.json']['path']);accepted=old['accepted_formed_stages'];revision=old_pointer['revision']+1
        else:
            old=None;revision=1;accepted=[]
            choice=np.asarray(np.load(ROOT/first['artifacts']['selected.npy']['path'],mmap_mode='r',allow_pickle=False)).copy()
            quality,trajectory=endpoint_arrays(base_scores,base_trajectory,choice)
            cache=read(ROOT/'analysis/first42_selected_edits_v1'/a.cohort/'SUMMARY.json')
            assert cache['status']=='PASS_FIRST42_SELECTED_EDIT_ANALYSIS_CACHE' and cache['complete_population'] and cache['cases']==count
            assert cache['source_summary_sha256']==sha(source)
            artifact=cache['artifacts']['selected_edits.npy'];assert sha(ROOT/artifact['path'])==artifact['sha256'];edits=np.asarray(np.load(ROOT/artifact['path'])).copy()
            catalog=[dict(id=ident,source_stage='runs/'+first['stage'],definition_pack=str(first_pack.relative_to(ROOT)),definition_pack_sha256=sha(first_pack)) for ident in ids]
        prior_ids={item['id'] for item in accepted};updates=[]
        for setting in sorted(read(ROOT/'runs/ELASTIC_STAGE_QUEUE.json')['stages'],key=lambda x:(x['priority'],x['id'])):
            if setting['id'] in prior_ids:continue
            stage=ROOT/setting['stage'];acceptance=stage/'AGENT_ACCEPTANCE.json'
            if not acceptance.exists():continue
            record=read(acceptance)
            if record['status']!='PASS_COMPLETE_AUDITED_FORMED_PACK':continue
            path=ROOT/record['summary'];assert sha(path)==record['summary_sha256'];current=read(path)
            if current['cohort']!=a.cohort:continue
            assert current['cases']==count and current['seeds']==[0,1,2,3,4] and current['rows_sha256']==first['rows_sha256'] and current['GT_used'] is False
            assert current['R3_selection_uses_S0S2_only'] and current['R3_S3S4_negative_results_retained']
            for value in current['artifacts'].values():assert sha(ROOT/value['path'])==value['sha256']
            def load_current(name):return np.load(ROOT/current['artifacts'][name]['path'],mmap_mode='r',allow_pickle=False)
            q=load_current('scores.npy');c=load_current('selected.npy');amount=load_current('selected_edits.npy');t=load_current('winner_trajectories.npy');ix=np.arange(count)
            new_q=np.stack([np.stack([q[ix,c[:,j],j] for j in range(5)],axis=1),q[ix,c[:,5]],q[ix,c[:,6]]],axis=1)
            book=[dict(id=ident,source_stage=setting['stage'],definition_pack=str(Path(current['pack']).relative_to(ROOT)),definition_pack_sha256=current['pack_sha256']) for ident in current['candidate_ids']]
            changes=merge(quality,trajectory,choice,edits,catalog,new_q,t,c,amount,book)
            item=dict(id=setting['id'],summary=str(path.relative_to(ROOT)),summary_sha256=record['summary_sha256'],pack_sha256=current['pack_sha256'])
            accepted.append(item);updates.append(dict(**item,endpoint_choice_changes=changes));prior_ids.add(setting['id'])
        if old_pointer and not updates:
            print(json.dumps(dict(status='NO_NEW_ACCEPTED_FORMED_STAGES',cohort=a.cohort,revision=old_pointer['revision'])));return
        groups={'navtrain_all' if a.cohort=='navtrain' else 'navtest':list(range(count))}
        if a.cohort=='navtrain':
            groups.update({name:[i for i,row in enumerate(rows) if row['subset']==name] for name in ['exploration','validation']})
        results={name:statistics(quality,baseline,rows,ix) for name,ix in groups.items()}
        u1=(quality[:,0,:,0]<.9).any(1);u2=quality[:,1,:,0].mean(1)<.9
        r3u1=(quality[:,0,:3,0]<.9).any(1);r3u2=quality[:,2,:3,0].mean(1)<.9
        destination=folder/('revision%04d'%revision);assert not destination.exists()
        work=folder/('.revision%04d.building_%s'%(revision,uuid.uuid4().hex));work.mkdir()
        for name,value in [('quality.npy',quality),('trajectories.npy',trajectory),('choice.npy',choice),('selected_edits.npy',edits)]:
            with (work/name).open('xb') as stream:np.save(stream,value,allow_pickle=False)
        atomic(work/'CATALOG.json',catalog)
        atomic(work/'UNRESOLVED_POOLS.json',dict(cohort=a.cohort,threshold=.9,source='Complete accepted candidate union',
            U1_indices=np.flatnonzero(u1).tolist(),U2_indices=np.flatnonzero(u2).tolist(),union_indices=np.flatnonzero(u1|u2).tolist(),
            R3_first_three_U1_indices=np.flatnonzero(r3u1).tolist(),R3_first_three_U2_indices=np.flatnonzero(r3u2).tolist(),R3_first_three_union_indices=np.flatnonzero(r3u1|r3u2).tolist(),
            test_cannot_supply_expansion_pool=a.cohort=='navtest',formed_candidates_exempt_from_prescreen=True))
        artifacts={name:dict(path=str((destination/name).relative_to(ROOT)),sha256=sha(work/name)) for name in
            ['quality.npy','trajectories.npy','choice.npy','selected_edits.npy','CATALOG.json','UNRESOLVED_POOLS.json']}
        result=dict(status='PASS_AUDITED_LIBRARY_LIVE_BEST',time=stamp(),cohort=a.cohort,cases=count,candidate_ids=len(catalog),
            first42_summary_sha256=sha(source),accepted_formed_stages=accepted,updates=updates,artifacts=artifacts,results=results,
            rows=first['rows'],rows_sha256=first['rows_sha256'],teacher_snapshot_frozen=False,new_teacher_snapshot_created=False,
            first42_student_teacher_unchanged=True,GT_assisted_per_scene_optimization_included=False,
            test_used_for_candidate_expansion=False,R3_heldout_results_not_used_for_selection=True,
            arrays_endpoint_axis=['R1','R2','R3'],choice_columns=['R1_S0','R1_S1','R1_S2','R1_S3','R1_S4','R2','R3'])
        atomic(work/'SUMMARY.json',result);work.rename(destination)
        atomic(pointer,dict(status='LIVE_ANALYSIS_POINTER_NOT_TEACHER_SNAPSHOT',time=stamp(),revision=revision,
            summary=str((destination/'SUMMARY.json').relative_to(ROOT)),summary_sha256=sha(destination/'SUMMARY.json')))
        print(json.dumps(dict(status=result['status'],cohort=a.cohort,revision=revision,candidate_ids=len(catalog),accepted_formed_stages=len(accepted),
            results={name:{key:round(value['PDMS'],6) for key,value in item['endpoints'].items()} for name,item in results.items()})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cohort',choices=['navtrain','navtest'],required=True);main(p.parse_args())
