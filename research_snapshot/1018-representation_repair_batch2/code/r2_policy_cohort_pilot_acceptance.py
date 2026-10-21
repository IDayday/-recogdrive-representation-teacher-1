"""Audit real finite-cohort canonical projections before future-only adoption."""
from r2_common import *
from collections import Counter
import math
import statistics


def main():
    setup('policy_cohort_pilot_acceptance')
    config=read(ROOT/'config/POLICY_COHORT_EXECUTION_PROTOCOL_V1.json')
    assert sha(ROOT/'code/r2_policy_cohort.py')==config['executor_sha256']
    engineering=read(ROOT/config['engineering_proof'])
    assert sha(ROOT/config['engineering_proof'])==config['engineering_sha256']
    assert engineering['status']=='ALL16_EXACT_ENGINEERING_COHORTS_COMPLETE'
    assert engineering['all_trajectory_seed_score_choice_diagnostic_record_order_exact']
    rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    summary={};workers=set();logical_records=0
    for source in config['sources']:
        base=ROOT/'runs/policy_cohort_frontier_v1/pilot'/source['name']
        tasks=read(base/'tasks.json');assert len(tasks)==32
        sizes=Counter();durations=[];projected=0
        for task in tasks:
            assert sha(ROOT/task['definition'])==task['definition_sha256']
            definition=read(ROOT/task['definition'])
            receipt=read(base/'receipts'/(task['id']+'.json'))
            assert receipt['status']=='COMPLETE';workers.add(receipt['worker'])
            result=receipt['result'];sizes[result['original_tasks']]+=1
            if result['original_tasks']<2:continue
            physical=result['physical_result'];assert sha(ROOT/physical['path'])==physical['sha256']
            raw=read(ROOT/physical['path']);durations.append(raw['seconds'])
            lookup={(r['token'],r['arm'],r['seed_index']):r for r in raw['records']}
            assert len(lookup)==len(raw['records'])
            entries={e['task']['id']:e for e in definition['entries']}
            assert len(result['projections'])==result['original_tasks']
            for number,projection in enumerate(result['projections']):
                entry=entries[projection['id']];original=entry['task'];point=read(ROOT/original['point'])
                assert entry['handler']==source['handler'] and sha(ROOT/entry['handler'])==source['handler_sha256']
                canonical=ROOT/projection['stage'];path=canonical/'results'/(projection['id']+'.json')
                assert sha(path)==projection['sha256']
                value=read(path);assert value['task']==original and value['seconds']==0
                assert value['physical_cohort_sha256']==physical['sha256']
                own=read(canonical/'receipts'/(projection['id']+'.json'))
                owner=read(canonical/'claims'/projection['id']/'OWNER.json')
                assert own['policy_cohort']==task['id']==owner['policy_cohort']
                aliases={p['id']:'entry'+str(number)+'__'+p['id'] for p in point['policies']}
                expected_tokens=[rows[i]['token'] for i in point['panel'][original['start']:original['end']]]
                assert set(r['token'] for r in value['records'])==set(expected_tokens)
                for record in value['records']:
                    assert record['seed']==seed(record['token'],record['seed_index'])
                    assert record['seed_index'] in point['seeds']
                    other=lookup[(record['token'],aliases.get(record['arm'],record['arm']),record['seed_index'])]
                    assert dict(other,arm=record['arm'])==record
                    # All numerical values in the complete trajectory and score dictionary are finite.
                    def finite(v):
                        if isinstance(v,dict):return all(finite(x) for x in v.values())
                        if isinstance(v,list):return all(finite(x) for x in v)
                        return not isinstance(v,float) or math.isfinite(v)
                    assert finite(record)
                logical_records+=len(value['records']);projected+=1
        assert sum(sizes.values())==32 and sizes[4]>=24,(source['name'],sizes)
        assert not list((base/'failures').glob('*.json'))
        summary[source['name']]=dict(cohorts=32,actual_logical_tasks_by_cohort_size=dict(sizes),
            projected_tasks_audited=projected,median_physical_seconds=statistics.median(durations),
            total_physical_seconds=sum(durations))
    output=dict(status='PASS',time=stamp(),sources=summary,distinct_workers=len(workers),
        logical_records_exactly_projected=logical_records,engineering_proof=config['engineering_proof'],
        executor_sha256=config['executor_sha256'],canonical_atomic_claims_verified=True,
        source_handlers_unchanged=True,own_policy_sets_preserved=True,
        physical_time_counted_once=True,not_a_new_speedup_estimate=True,
        decision='Adopt only future unclaimed tasks for these two original sources; preserve in-flight tasks and all results.')
    atomic(ROOT/'provenance/POLICY_COHORT_FINITE_PILOT_ACCEPTANCE.json',output)
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()
