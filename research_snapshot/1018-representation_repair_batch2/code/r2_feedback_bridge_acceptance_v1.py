"""Accept a scores-only pilot bridge without changing any prior statistic."""
from r2_common import *


def main():
    setup('feedback_bridge_acceptance')
    before = read(ROOT/'analysis/expert_feedback_distribution_v2/BEFORE_V1_POINTER.json')
    after = read(ROOT/'analysis/expert_feedback_distribution_v2/LATEST.json')
    for pointer in (before, after):
        assert sha(ROOT/pointer['path']) == pointer['sha256']
    old, new = (read(ROOT/p['path']) for p in (before, after))
    fields = ('system', 'heldout_fold', 'role', 'dataset', 'quality_class', 'seed_index', 'expert')
    def indexed(records):
        result = {tuple(r[k] for k in fields): r for r in records}
        assert len(result) == len(records)
        return result
    left, right = indexed(old['records']), indexed(new['records'])
    assert left.keys() <= right.keys()
    assert all(digest(value) == digest(right[key]) for key, value in left.items())
    added = [right[k] for k in right.keys()-left.keys()]
    expected = {f'correction_capacity_{bank}_K3_seed0' for bank in ('r32_b1', 'r128_b1', 'r128_b4')}
    assert len(added) == 432
    assert {r['system'] for r in added} == expected
    assert all(r['heldout_fold'] == 0 for r in added)
    assert all(new[k] == 0 for k in ('new_model_training', 'new_rollouts', 'new_scoring'))
    rows = []
    for bank in ('r32_b1', 'r128_b1', 'r128_b4'):
        for fit in range(3):
            system = f'correction_capacity_{bank}_K3_seed{fit}'
            record = dict(system=system)
            oracle, forced = [], []
            for dataset in ('fitting_pool_S0', 'outer_held_S0S1S2'):
                matching = [r for r in new['own_K_Oracle_summaries']
                    if r['system'] == system and r['role'] == 'PDMS'
                    and r['dataset'] == dataset and r['quality_class'] == 'S0_failure'
                    and r['seed_index'] == 0]
                assert len(matching) == 1 and matching[0]['complete_fivefold']
                oracle.append(matching[0]['mean_PDMS_gain'])
                high = [r for r in new['records'] if r['system'] == system
                    and r['role'] == 'PDMS' and r['dataset'] == dataset
                    and r['quality_class'] == 'S0_high' and r['seed_index'] == 0
                    and r['expert'] != 'own_K_Oracle']
                assert len(high) == 15
                assert {r['heldout_fold'] for r in high} == set(range(5))
                assert all(r['active_K'] == 3 for r in high)
                forced.append(sum(r['cases']*r['mean_PDMS_gain'] for r in high)
                              / sum(r['cases'] for r in high))
            record.update(conditional_failure_ownK_Oracle_train_then_held=oracle,
                          conditional_high_forced_random_singleexpert_train_then_held=forced)
            rows.append(record)
    directory = ROOT/'analysis/expert_feedback_distribution_v2'
    proof = dict(status='PASS_OLD_RECORDS_UNCHANGED_PILOT_FOLD0_COMPLETE', time=stamp(),
        before=before, after=after, old_records=len(left), new_records=len(right),
        exactly_preserved_old_records=len(left), new_pilot_records=len(added),
        pilot_bridge_manifest_sha256=new['pilot_bridge_manifest_sha256'],
        complete_capacity_systems=len(rows), new_training=0, new_rollouts=0, new_scoring=0,
        implementation=str(Path(__file__).relative_to(ROOT)), implementation_sha256=sha(Path(__file__)))
    atomic(directory/'BRIDGE_ACCEPTANCE.json', proof)
    atomic(ROOT/'analysis/capacity_replication/COMPLETE_TRAIN_HELD_CANDIDATE_DIAGNOSTIC_V2.json',
        dict(time=stamp(), feedback_snapshot=after, rows=rows,
             conditional_not_natural_overall=True, ownK_Oracle_uses_true_score=True,
             forced_H_is_uniform_random_choice_of_one_complete_expert_trajectory=True,
             not_hidden_or_coordinate_mixture=True,
             pilot_fold0_previously_used_in_exploratory_capacity_promotion=True,
             scope='Descriptive different-scene fittingpool versus held comparison. '
                   'Repeated fittingpool views are not independent cases. No causal overfit '
                   'claim or independent confirmation. No additional rollout or scoring.'))
    current = read(ROOT/'analysis/expert_feedback_distribution/LATEST.json')
    assert current in (before, after), 'Concurrent pointer update must be reviewed'
    atomic(ROOT/'analysis/expert_feedback_distribution/LATEST.json', after)
    print(json.dumps(dict(status=proof['status'], old_records=len(left), new_records=len(right),
                          complete_capacity_systems=len(rows), rows=rows)), flush=True)


if __name__ == '__main__':
    main()
