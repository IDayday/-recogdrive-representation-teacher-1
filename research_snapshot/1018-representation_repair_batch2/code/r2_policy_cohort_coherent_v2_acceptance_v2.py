"""First-stage audit of future-only shared-scene canonical results."""
from r2_common import *
from collections import Counter
import math


def main():
    setup('policy_cohort_full_acceptance')
    config=read(ROOT/'config/POLICY_COHORT_COHERENT_EXECUTION_PROTOCOL_V2.json')
    assert sha(ROOT/'code/r2_policy_cohort.py')==config['executor_sha256']
    rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    workers=set();summaries={};records=0
    for source in config['sources']:
        base=ROOT/'runs/policy_cohort_coherent_frontier_v2/full'/source['name']
        completed=[t for t in read(base/'tasks.json') if (base/'receipts'/(t['id']+'.json')).exists()][:40]
        assert len(completed)==40
        sizes=Counter();systems=set();panels=set();audited=0
        for task in completed:
            assert sha(ROOT/task['definition'])==task['definition_sha256']
            definition=read(ROOT/task['definition']);receipt=read(base/'receipts'/(task['id']+'.json'))
            assert receipt['status']=='COMPLETE';workers.add(receipt['worker']);r=receipt['result'];sizes[r['original_tasks']]+=1
            if r['original_tasks']==0:continue
            if r['original_tasks']==1:
                physical=r['physical_result'];assert r['single_original_fallback'] and sha(ROOT/physical['path'])==physical['sha256']
                raw=read(ROOT/physical['path']);original=raw['task'];entry=next(e for e in definition['entries'] if e['task']['id']==original['id']);point=read(ROOT/original['point'])
                assert entry['task']==original and sha(ROOT/entry['handler'])==source['handler_sha256']
                canonical=ROOT/entry['stage'];owner=read(canonical/'claims'/original['id']/'OWNER.json');own=read(canonical/'receipts'/(original['id']+'.json'))
                assert owner['policy_cohort']==task['id']==own['policy_cohort'] and own['compute_mode']=='unchanged_single_original_task'
                systems.add(point['system']);panels.add(point['heldout_fold'])
                selectedrows=[rows[i] for i in point['panel'][original['start']:original['end']]]
                assert all(row['subset']=='exploration' for row in selectedrows)
                if point['mode']=='heldout':
                    assert point['heldout_fold']>=0 and all(int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5==point['heldout_fold'] for row in selectedrows)
                else:assert point['mode']=='training' and point['heldout_fold']==-1
                assert set(v['token'] for v in raw['records'])==set(row['token'] for row in selectedrows)
                for spec in point['policies']:assert sha(ROOT/spec['policy'])==spec['policy_sha256']
                for v in raw['records']:
                    assert v['seed']==seed(v['token'],v['seed_index']) and len(v['trajectory'])==8
                    assert all(len(t)==3 and all(math.isfinite(x) for x in t) for t in v['trajectory'])
                    assert all(math.isfinite(x) for x in v['score'].values())
                audited+=1;records+=len(raw['records']);continue
            physical=r['physical_result'];assert sha(ROOT/physical['path'])==physical['sha256']
            raw=read(ROOT/physical['path']);lookup={(v['token'],v['arm'],v['seed_index']):v for v in raw['records']}
            entries={e['task']['id']:e for e in definition['entries']}
            for n,projection in enumerate(r['projections']):
                e=entries[projection['id']];original=e['task'];point=read(ROOT/original['point'])
                assert sha(ROOT/e['handler'])==source['handler_sha256']
                systems.add(point['system']);panels.add(point['heldout_fold'])
                canonical=ROOT/e['stage'];p=canonical/'results'/(original['id']+'.json')
                assert sha(p)==projection['sha256'];value=read(p);assert value['task']==original
                assert value['physical_cohort_source']==physical['path'] and value['physical_cohort_sha256']==physical['sha256']
                assert read(canonical/'claims'/original['id']/'OWNER.json')['policy_cohort']==task['id']
                assert read(canonical/'receipts'/(original['id']+'.json'))['policy_cohort']==task['id']
                selectedrows=[rows[i] for i in point['panel'][original['start']:original['end']]]
                assert all(row['subset']=='exploration' and int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5==point['heldout_fold'] for row in selectedrows)
                assert set(v['token'] for v in value['records'])==set(row['token'] for row in selectedrows)
                aliases={p['id']:'entry'+str(n)+'__'+p['id'] for p in point['policies']}
                for spec in point['policies']:
                    assert sha(ROOT/spec['policy'])==spec['policy_sha256'];policy=read(ROOT/spec['policy'])
                    assert policy['heldout_fold']==point['heldout_fold']
                    assert all(part['slot']>=0 for part in policy['parts'])
                for v in value['records']:
                    assert v['seed']==seed(v['token'],v['seed_index'])
                    assert dict(lookup[v['token'],aliases.get(v['arm'],v['arm']),v['seed_index']],arm=v['arm'])==v
                    assert len(v['trajectory'])==8 and all(len(t)==3 and all(math.isfinite(x) for x in t) for t in v['trajectory'])
                    assert all(math.isfinite(x) for x in v['score'].values())
                audited+=1;records+=len(value['records'])
        assert audited>=40 and sum(n for size,n in sizes.items() if size>=2)>=1
        assert not list((base/'failures').glob('*.json'))
        summaries[source['name']]=dict(physical_cohorts=40,actual_cohort_sizes=dict(sizes),canonical_tasks_audited=audited,systems=sorted(systems),heldout_folds=sorted(panels))
    proof=dict(status='PASS',time=stamp(),first_phase=read(ROOT/'analysis/policy_cohort_coherent_v2/FIRST_FIVE_MINUTE_PHASE_READY.json'),
        sources=summaries,distinct_workers=len(workers),complete_records_audited=records,source_handlers_unchanged=True,
        canonical_projection_exact=True,exploration_held_session_isolation_verified=True,
        no_scientific_model_seed_trajectory_score_or_own_policy_change=True,not_a_throughput_benchmark=True)
    atomic(ROOT/'provenance/POLICY_COHORT_COHERENT_V2_FIRST_PHASE_ACCEPTANCE.json',proof)
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':main()
