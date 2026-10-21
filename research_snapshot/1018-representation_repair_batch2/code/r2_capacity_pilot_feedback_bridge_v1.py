"""Recover pilot candidate scores for descriptive feedback auditing, without model work.

Writes only a dedicated analysis directory, never a live producer's selection or
response inbox. The historical fold0 was used in capacity exploration, and is
not independent confirmation. All candidate/role identities remain unchanged.
"""
from r2_common import *


def main():
    setup('capacity_pilot_feedback_bridge_v1')
    import numpy as np
    from r2_point_response import FIELDS
    from r2_expert_space import save_npz
    destination=ROOT/'analysis/capacity_replication/pilot_feedback_bridge_v1'
    assert not destination.exists()
    pointpath='runs/capacity_observable_held_candidate_v1/points/capacity_observable_held_candidate.json'
    point=read(ROOT/pointpath);stage=ROOT/'runs/capacity_observable_held_candidate_v1'
    assert point['mode']=='heldout' and point['heldout_fold']==0 and point['seeds']==[0,1,2]
    rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    assert len(point['panel'])==1135
    assert all(rows[i]['subset']=='exploration' and int(digest(dict(session=rows[i]['session'],cv_root=20261016))[:8],16)%5==0 for i in point['panel'])
    parts={};policy_sources=[]
    for config in point['policies']:
        path=ROOT/config['policy'];policy=read(path);assert sha(path)==config['policy_sha256']
        for part in policy['parts']:parts[part['id']]=part
        policy_sources.append(dict(path=config['policy'],sha256=sha(path)))
    ids=['baseline']+sorted(parts);arms={v:i for i,v in enumerate(ids)}
    cases={rows[i]['token']:j for j,i in enumerate(point['panel'])};seeds={j:j for j in point['seeds']}
    scores=np.full((len(cases),len(ids),len(seeds),len(FIELDS)),np.nan);seen=set();sources=[]
    tasks=[t for t in read(stage/'tasks.json') if t['point']==pointpath]
    assert tasks
    for task in tasks:
        assert (stage/'receipts'/(task['id']+'.json')).exists()
        path=stage/'results'/(task['id']+'.json');data=read(path)
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
        for record in data['records']:
            arm=record['arm']
            if arm!='baseline' and not arm.startswith('candidate_'):continue
            arm='baseline' if arm=='baseline' else arm[len('candidate_'):]
            key=(cases[record['token']],arms[arm],seeds[record['seed_index']])
            assert key not in seen;seen.add(key)
            scores[key]=[record['score'][field] for field in FIELDS]
    assert len(seen)==len(cases)*len(ids)*len(seeds) and np.isfinite(scores).all()
    oldpath='analysis/responses/capacity_observable_held_candidate_v1/capacity_observable_held_candidate.json'
    old=read(ROOT/oldpath);assert old['fields']==FIELDS and sha(ROOT/old['matrix'])==old['matrix_sha256']
    with np.load(ROOT/old['matrix']) as data:
        assert np.array_equal(data['global_indices'],point['panel']) and np.array_equal(data['seeds'],point['seeds'])
        base=list(data['arm_ids']).index('baseline');assert np.array_equal(scores[:,0],data['scores'][:,base])
    destination.mkdir(parents=True)
    matrix=destination/'SCORES.npz'
    hashed=save_npz(matrix,global_indices=np.asarray(point['panel']),arm_ids=np.asarray(ids),seeds=np.asarray(point['seeds']),scores=scores)
    aliases=[]
    for name in ['capacity_r32_b1','capacity_r128_b1','capacity_r128_b4']:
        source=ROOT/'expert_capacity_observable/selections'/(name+'.json');selection=read(source)
        assert selection['heldout_fold']==0 and selection['K']==3
        for role,owned in selection['policies'].items():
            assert len(owned)==3 and len(set(owned.values()))==3
            assert all(ident in arms for ident in owned.values())
        selected=destination/'selections'/(name+'.json')
        atomic(selected,dict(selection,diagnostic_training_responses=[
            'analysis/responses/capacity_observable_feedback_S0_v1/capacity_observable_train_union.json',
            'analysis/responses/capacity_observable_feedback_noise_v1/capacity_observable_train_union.json'],
            actual_historical_selection=str(source.relative_to(ROOT)),actual_historical_selection_sha256=sha(source),
            analysis_only_not_a_live_producer_input=True))
        bank=destination/'held_banks'/(name+'.json')
        atomic(bank,dict(status='COMPLETE_SCORES_ONLY_DIAGNOSTIC_REUSE',time=stamp(),system=selection['system'],
            heldout_fold=0,mode='heldout',point=pointpath,matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,
            fields=FIELDS,actual_raw_candidate_sources=sources,physical_union_is_not_a_policy=True,
            exact_ownK_selection=str(selected.relative_to(ROOT)),no_model_execution_or_new_scoring=True,
            historical_exploratory_fold_used_for_capacity_promotion=True))
        aliases.append(dict(selection=str(selected.relative_to(ROOT)),selection_sha256=sha(selected),bank=str(bank.relative_to(ROOT)),bank_sha256=sha(bank)))
    atomic(destination/'MANIFEST.json',dict(status='PASS_LOSSLESS_HISTORICAL_PILOT_CANDIDATE_SCORE_REUSE',time=stamp(),
        original_point=pointpath,original_point_sha256=sha(ROOT/pointpath),source_policy_files=policy_sources,
        raw_scored_source_chunks=sources,matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,cases=len(cases),
        physical_candidate_arms=len(parts),aliases=aliases,Base_scores_exact_to_existing_pilot_matrix=True,
        no_new_model_training_or_inference_or_scoring=True,no_live_queue_response_or_selection_mutated=True,
        scope='Descriptive exploration only; each role retains its own K3, no unionOracle or independent confirmation.'))
    print(json.dumps(dict(status='PASS',cases=len(cases),candidate_arms=len(parts),actual_raw_scored_records=len(seen),aliases=len(aliases))))


if __name__=='__main__':main()
