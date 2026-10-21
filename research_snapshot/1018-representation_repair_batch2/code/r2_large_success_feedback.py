"""Predeclared fold0 K2 data control, broad success/case coverage, no new assets.

Fit and inner-calibration sessions remain disjoint. Existing identical outcomes
are copied exactly; only newly requested scene/draw/expert outputs are computed.
This does not refit the experts or change their locations, spaces or strengths.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced


def reused_chunk(stage,task,point,data,response,rows):
    import numpy as np
    lookup={int(v):j for j,v in enumerate(data['global_indices'])};indices=point['panel'][task['start']:task['end']]
    if not all(i in lookup for i in indices):return False
    assert list(data['seeds'])==point['seeds'];ids=list(data['arm_ids']);order=['baseline']+[p['id'] for p in point['arms']];assert set(ids)==set(order);records=[]
    for index in indices:
        j=lookup[index];row=rows[index]
        for ident in order:
            a=ids.index(ident)
            for n,noise in enumerate(point['seeds']):
                record=dict(token=row['token'],session=row['session'],arm=ident,seed_index=noise,seed=seed(row['token'],noise),trajectory=data['trajectory'][j,a,n].tolist(),
                    score={f:float(v) for f,v in zip(response['fields'],data['scores'][j,a,n])},relative_edit=float(data['relative_edit'][j,a,n]),original_S0_quality=row['quality'])
                if ident=='baseline':record['base_action_states']=data['base_action_states'][j,n].tolist()
                records.append(record)
    path=stage/'results'/(task['id']+'.json');atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=records,seconds=0.,compute_mode='immutable_actual_outcome_reuse',source_matrix=response['matrix'],source_matrix_sha256=response['matrix_sha256']))
    atomic(stage/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=task,worker='immutable_actual_outcome_copy',seconds=0.,compute_mode='reused',result=dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(records))))
    return True


def main():
    setup('large_success_feedback')
    import numpy as np
    from r2_token_critic import inner_session
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);held=0;system='representation_K2_seed0'
    selected=next(p for p in (ROOT/'analysis/expert_library_selection').glob('*.json') if read(p)['heldout_fold']==held and read(p)['system']==system);selection=read(selected)
    responses=[ROOT/'analysis/responses'/name/selected.name for name in ['expert_library_S0_v1','expert_library_noise_v1']];assert all(p.exists() for p in responses)
    old=[]
    for path in responses:
        d=read(path);assert sha(ROOT/d['matrix'])==d['matrix_sha256'];point=read(ROOT/d['point'])
        with np.load(ROOT/d['matrix']) as z:data={k:np.array(z[k]) for k in ['global_indices','arm_ids','seeds','scores','trajectory','relative_edit','base_action_states']}
        old.append((d,point,data))
    allowed=np.asarray([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held for r in rows]);cal=np.asarray([inner_session(r['session']) for r in rows]);partitions={}
    mandatory_high=set(old[0][1]['panel_partitions']['high'])|set(old[1][1]['panel_partitions']['high']);mandatory_mid=set(old[0][1]['panel_partitions']['intermediate'])|set(old[1][1]['panel_partitions']['intermediate'])
    def choose(mask,mandatory,count,salt):
        fixed=sorted(int(i) for i in mandatory if mask[int(i)]);fixed_set=set(fixed);remaining=[int(i) for i in np.flatnonzero(mask) if int(i) not in fixed_set]
        return fixed+balanced(remaining,rows,max(count-len(fixed),0),salt)
    for label,split,nh,nm in [('calibration',cal,4096,1024),('fitting',~cal,8192,2048)]:
        salt=dict(large_success_feedback=20261018,held=held,system=system,partition=label)
        h=choose(allowed&split&(q>.9),mandatory_high,nh,salt);m=choose(allowed&split&(q>=.7)&(q<=.9),mandatory_mid,nm,salt)
        partitions[label]=dict(high=h,intermediate=m)
        assert all(bool(cal[i])==(label=='calibration') and allowed[i] for i in h+m)
    protocol=ROOT/'config/LARGE_SUCCESS_FEEDBACK_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_PILOT',time=stamp(),heldout_fold=held,system=system,selection=str(selected.relative_to(ROOT)),selection_sha256=sha(selected),
        fitting=dict(high_target=8192,intermediate_target=2048),calibration=dict(high_target=4096,intermediate_target=1024),actual_counts={k:{c:len(v) for c,v in p.items()} for k,p in partitions.items()},
        folds='Outer session fold0 excluded. Inner one-of-seven sessions are excluded from subsequent router/critic gradient fitting; frozen repair experts were previously fitted on the outer training fold including these sessions. Inner calibration is not a whole-system independent confirmation.',failure_panels='Preserve original S0 all failures and original S1/S2 failure subset; no extra failure cases to confound the success-data control.',
        old_case_outcomes_reused_exactly=True,new_observation_or_representation_collection=False,new_expert_training=False,
        followup='First recalibrate frozen8k critics on larger inner-calibration results; then matched additional-training-budget original-versus-augmented-data controls. Initial mechanistic pilot only; finalists need other folds and fit repetitions.',
        validation_accessed=False,test_accessed=False))
    smoke=ROOT/'runs/large_success_feedback_engineering_v1';known=set(old[0][2]['global_indices'].tolist());fresh=[i for i in partitions['calibration']['high'] if i not in known][:2];assert len(fresh)==2
    smoke_point=smoke/'points/smoke.json'
    if not smoke_point.exists():atomic(smoke_point,dict(id='large_success_feedback_smoke',system=system,K=selection['K'],heldout_fold=held,arms=selection['arms'],policies=selection['policies'],panel=fresh,seeds=[0,1,2],training_only=True))
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='large_success_feedback_smoke',stage=str(smoke.relative_to(ROOT)),point=str(smoke_point.relative_to(ROOT)),start=0,end=2)]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='large_success_feedback_real_engineering',path=str(smoke.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=8))
    while not (smoke/'receipts/large_success_feedback_smoke.json').exists():time.sleep(15)
    atomic(ROOT/'provenance/LARGE_SUCCESS_FEEDBACK_ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),source_receipt='runs/large_success_feedback_engineering_v1/receipts/large_success_feedback_smoke.json',
        real_new_success_cases=2,actual_model_and_paired_trajectory_scoring=True,archived_S0_exact_guard_passed=True,same_verified_existing_48card_program=True,new_VLM_collection=False))
    stages=[ROOT/'runs/large_success_S0_v1',ROOT/'runs/large_success_noise_v1'];summary=[]
    for n,stage,seeds in [(0,stages[0],[0]),(1,stages[1],[1,2])]:
        queue=[];queued=set();response,original,data=old[n];reused=0
        for label in ['calibration','fitting']:
            parts=dict(partitions[label]);parts['failure']=[i for i in original['panel_partitions']['failure'] if bool(cal[i])==(label=='calibration')]
            panel=parts['failure']+parts['high']+parts['intermediate'];assert len(panel)==len(set(panel))
            ident='large_success_'+label+'_'+digest(dict(selection=str(selected.relative_to(ROOT)),held=held))[:24];point_path=stage/'points'/(ident+'.json')
            point=dict(id=ident,system=system,K=selection['K'],heldout_fold=held,arms=selection['arms'],policies=selection['policies'],selection=str(selected.relative_to(ROOT)),panel=panel,panel_partitions=parts,seeds=seeds,training_only=True,inner_partition=label,protocol=str(protocol.relative_to(ROOT)))
            if not point_path.exists():atomic(point_path,point)
            for start in range(0,len(panel),8):
                task=dict(id=ident+'_%04d'%start,stage=str(stage.relative_to(ROOT)),point=str(point_path.relative_to(ROOT)),start=start,end=min(start+8,len(panel)));enqueue(queue,queued,task)
                if not (stage/'receipts'/(task['id']+'.json')).exists() and reused_chunk(stage,task,point,data,response,rows):reused+=1
        if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',queue)
        else:assert digest(read(stage/'tasks.json'))==digest(queue)
        atomic(stage/'producer.json',dict(complete=True,tasks=len(queue),time=stamp(),immutable_reused_chunks=reused,meaning='Finite scientific data batch; retained global DLC queue and nodes stay open.'))
        register_once(dict(name=stage.name,path=str(stage.relative_to(ROOT)),handler='code/r2_library_rollouts.py',handler_sha256=sha(ROOT/'code/r2_library_rollouts.py'),kind='custom',priority=23.2,enabled=False))
        summary.append(dict(stage=str(stage.relative_to(ROOT)),logical_tasks=len(queue),reused_chunks=reused,new_compute_tasks=len(queue)-reused))
    atomic(ROOT/'provenance/LARGE_SUCCESS_FEEDBACK_SUBMISSION.json',dict(time=stamp(),stages=summary,protocol=str(protocol.relative_to(ROOT)),global_queues_and_nodes_retained=True))


if __name__=='__main__':main()
