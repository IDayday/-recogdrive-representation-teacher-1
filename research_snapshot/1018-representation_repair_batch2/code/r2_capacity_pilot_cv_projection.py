"""Reuse completed matched pilot columns as explicit fold0 CV observations.

No model execution or invented receipts. Virtual method-stage labels let the
existing reviewer combine these identical algorithms with their other folds.
Every matrix retains its actual private pilot source and column map.
"""
from r2_common import *


def main():
    setup('capacity_pilot_cv_projection')
    import numpy as np
    from r2_expert_space import save_npz
    protocol=read(ROOT/'config/CAPACITY_REPLICATION_PROTOCOL_V1.json');rows=read(read(ROOT/'manifests/data_source.json')['rows']);outputs=[]
    methods=[('hard','hard','warm_hard_cv_v1',['observation','trajectory','denoising'],None),('candidate','candidate','candidate_selector_cv_v1',['trajectory','denoising'],None),('joint','joint_hard_continuous','additional_joint_policy_cv_v1',['observation','trajectory','denoising'],'hard_continuous'),('joint','joint_soft_joint','additional_joint_policy_cv_v1',['observation','trajectory','denoising'],'soft_joint')]
    for sourcekind,label,virtualstage,tiers,kind in methods:
        responsepath='analysis/responses/capacity_observable_held_'+sourcekind+'_v1/capacity_observable_held_'+sourcekind+'.json';response=read(ROOT/responsepath);assert sha(ROOT/response['matrix'])==response['matrix_sha256'];point=read(ROOT/response['point'])
        with np.load(ROOT/response['matrix']) as z:arrays={n:np.array(z[n]) for n in z.files}
        ids=list(arrays['arm_ids']);indices=arrays['global_indices'];assert len(indices)==1135 and list(arrays['seeds'])==[0,1,2]
        assert all(rows[int(i)]['subset']=='exploration' and int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5==0 for i in indices)
        for variant in protocol['variants']:
            system=f"correction_{variant['id']}_K3_seed0";ident='capacityrep_pilot_projection_'+digest(dict(system=system,method=label))[:24]
            names=[role+'_'+tier for role in ['PDMS','safety'] for tier in tiers];original=['baseline']+[variant['id']+'__'+label+'__'+n for n in names];columns=[ids.index(n) for n in original]
            policies=[]
            for name,old in zip(names,original[1:]):
                meta=point['policy_metadata'][old];assert meta['variant']==variant['id']
                policies.append(dict(id=name,actual_source_policy=meta['source_policy'],actual_source_policy_sha256=meta['source_policy_sha256']))
            dp=ROOT/'runs/capacity_replication_pilot_projection_v1/points'/(ident+'.json');assert not dp.exists()
            atomic(dp,dict(id=ident,system=system,heldout_fold=0,mode='heldout',kind=kind,policies=policies,panel=indices.tolist(),seeds=[0,1,2],derived_existing_scored_pilot=True,not_a_new_GPU_run=True,actual_source=responsepath,source_column_ids=original))
            dest=ROOT/'analysis/capacity_replication_pilot_projection'/(ident+'.npz');assert not dest.exists()
            projected={n:(v[:,columns] if n in ['scores','trajectory','relative_edit'] else v) for n,v in arrays.items()};projected['arm_ids']=np.asarray(['baseline']+names)
            hashed=save_npz(dest,**projected)
            with np.load(dest) as z:
                for n in ['scores','trajectory','relative_edit']:assert np.array_equal(z[n],arrays[n][:,columns])
            out=ROOT/'analysis/responses'/virtualstage/(ident+'.json');assert not out.exists()
            atomic(out,dict(status='COMPLETE',time=stamp(),task=dict(id='outcome_'+ident,stage='runs/'+virtualstage,actual_projection_stage='runs/capacity_replication_pilot_projection_v1',not_executed_as_original_GPU_task=True),
                point=str(dp.relative_to(ROOT)),matrix=str(dest.relative_to(ROOT)),matrix_sha256=hashed,cases=1135,arms=len(names),seeds=[0,1,2],fields=response['fields'],source_mode='heldout',independent_confirmation=False,
                derivation='Lossless column/arm-label projection of already completed actual scored pilot; no regenerated trajectories or synthetic receipts.',actual_source_response=responsepath,actual_source_response_sha256=sha(ROOT/responsepath),actual_source_matrix=response['matrix'],actual_source_matrix_sha256=response['matrix_sha256'],source_column_ids=original,
                selection_scope='Exploratory pilot used for capacity promotion, retained as exploratory CV rather than independent confirmation.',fold0_case_panel='Original matched candidate_outer_panel reused for all methods; other folds use existing method-specific predeclared panels, matched across capacities.',validation_accessed=False,test_accessed=False))
            outputs.append(dict(path=str(out.relative_to(ROOT)),sha256=sha(out),policies=len(names)))
    assert len(outputs)==12 and sum(v['policies'] for v in outputs)==66
    atomic(ROOT/'provenance/CAPACITY_PILOT_FOLD0_LOSSLESS_CV_PROJECTION.json',dict(status='PASS',time=stamp(),outputs=outputs,complete_policy_columns=66,original_records_unchanged=True,new_GPU_runs=0,no_original_receipts_created=True,scope='Development fold0 reuse, no independent confirmation claim'))
    print(json.dumps(dict(status='PASS',points=12,policies=66,new_GPU_runs=0)))


if __name__=='__main__':main()
