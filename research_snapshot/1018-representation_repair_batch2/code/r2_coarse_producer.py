"""Stream completed subgroup fits into a broad, training-only real-outcome sweep.

This producer never selects a deployable policy or accesses held-out outcomes.
It proposes locations from training descriptors, then retains actual responses.
"""
from r2_common import *
from collections import defaultdict


def balanced(indices, rows, count, salt):
    groups = defaultdict(list)
    for index in indices:
        groups[rows[int(index)]['session']].append(int(index))
    sessions = sorted(groups, key=lambda s: digest(dict(session=s, salt=salt)))
    for session in sessions:
        groups[session].sort(key=lambda i: digest(dict(token=rows[i]['token'], salt=salt)))
    result = []
    while len(result) < count:
        added = False
        for session in sessions:
            if groups[session]:
                result.append(groups[session].pop(0)); added = True
                if len(result) == count: break
        if not added: break
    return result


def arms_from_fits(fits):
    arms = []
    for fit in fits:
        for method in ['mean', 'contract', 'ot', 'quality', 'local', 'qda_gradient']:
            for strength, cap in [(.25, .005), (1., .02), (1., .1)]:
                spec = dict(block=fit['block'], group=fit['group'], method=method,
                            alpha=strength, cap=cap, gate='none', fit_path=fit['path'],
                            fit_sha256=fit['sha256'])
                arms.append(dict(id='arm_' + digest(spec)[:22], **spec))
        for method in ['remove', 'project', 'soft_clip']:
            spec = dict(block=fit['block'], group=fit['group'], method=method,
                        alpha=1., cap=.02, gate='none', fit_path=fit['path'],
                        fit_sha256=fit['sha256'])
            arms.append(dict(id='arm_' + digest(spec)[:22], **spec))
    assert len({a['id'] for a in arms}) == len(arms)
    return arms


def main():
    setup('coarse_producer')
    import numpy as np
    source = read(ROOT/'manifests/data_source.json'); rows = read(source['rows'])
    quality = np.load(source['quality'])
    explore = np.array([r['subset'] == 'exploration' for r in rows])
    high = np.flatnonzero(explore & (quality > .9))
    middle = np.flatnonzero(explore & (quality >= .7) & (quality <= .9))
    protocol = read(ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json')
    tasks = protocol['tasks']
    base = ROOT/'runs/representation_coarse_v1'
    base.mkdir(parents=True, exist_ok=True)
    state_path = base/'producer.json'
    assert not state_path.exists(), 'Use a new stage identity, never overwrite a prior producer.'
    atomic(base/'tasks.json', [])
    atomic(state_path, dict(status='PRODUCING', complete=False, tasks=0, points=0, time=stamp()))
    atomic(base/'PROTOCOL.json', dict(status='FROZEN', time=stamp(), points_expected=len(tasks),
           panel=dict(group_failure=16, other_failure=8, high_success=4, intermediate=4),
           methods=['mean','contract','ot','quality','local','qda_gradient','remove','project','soft_clip'],
           seeds=[0], strength_cap_pairs=[[.25,.005],[1.,.02],[1.,.1]],
           fitted_groups='training only', actual_outcome_cv=False,
           interpretation='Exploratory allocation only. Whole-system fold-contained CV must follow.',
           validation_accessed=False, test_accessed=False, all_layers_preserved=True))
    group_cache = {}; handled = set(); queue = []; points = 0; ineligible = []
    handler = 'code/r2_eval_rollouts.py'; version = sha(ROOT/handler)
    # Parent workers persist through incremental production, and elastic nodes
    # join the same atomic subqueue without a fixed rank count or node barrier.
    append('gpu', [dict(id='representation_coarse_worker_%03d'%i, handler=handler,
                         handler_sha256=version, stage=str(base.relative_to(ROOT))) for i in range(96)])
    while len(handled) < len(tasks):
        changed = False
        for task in tasks:
            if task['id'] in handled: continue
            path = ROOT/'analysis/expert_spaces'/(task['id']+'.json')
            if not path.exists(): continue
            result = read(path); handled.add(task['id']); changed = True
            if result['status'] != 'PASS':
                ineligible.append(dict(id=task['id'], status=result['status'])); continue
            group_name = task['responsibility_meta']
            if group_name not in group_cache:
                meta = read(ROOT/group_name)
                with np.load(ROOT/meta['path']) as z:
                    group_cache[group_name] = (np.array(z['global_indices']), np.array(z['responsibility']))
            indices, responsibility = group_cache[group_name]
            dominant = np.argmax(responsibility, axis=1) == task['expert']
            salt = dict(system=group_name, expert=task['expert'], panel=20261018)
            own = balanced(indices[dominant], rows, 16, salt)
            # Small groups retain their strongest soft members, without removing
            # failures that were difficult to classify or repair.
            if len(own) < 16:
                order = np.argsort(-responsibility[:,task['expert']])
                own += [int(indices[i]) for i in order if int(indices[i]) not in own][:16-len(own)]
            other = balanced([i for i in indices[~dominant] if i not in own], rows, 8, salt)
            success = balanced(high, rows, 4, salt)
            mid = balanced(middle, rows, 4, salt)
            panel = own + other + success + mid
            assert len(panel) == len(set(panel)) and all(rows[i]['subset']=='exploration' for i in panel)
            descriptor = dict(id=task['id'], task=task, fit_metadata=result['fits'],
                              arms=arms_from_fits(result['fits']), panel=panel, seeds=[0],
                              panel_partitions=dict(own=own, other=other, success=success, intermediate=mid),
                              training_only=True, actual_outcome_cv=False)
            point_path = base/'points'/(task['id']+'.json'); atomic(point_path, descriptor)
            for start in range(0, len(panel), 4):
                queue.append(dict(id=task['id']+'_%03d'%start, point=str(point_path.relative_to(ROOT)),
                                  start=start, end=min(start+4,len(panel))))
            points += 1
        if changed:
            atomic(base/'tasks.json', queue)
            atomic(state_path, dict(status='PRODUCING', complete=False, tasks=len(queue), points=points,
                   handled=len(handled), expected=len(tasks), ineligible=ineligible, time=stamp()))
        if len(handled) < len(tasks): time.sleep(30)
    atomic(state_path, dict(status='PRODUCER_COMPLETE', complete=True, tasks=len(queue), points=points,
           handled=len(handled), expected=len(tasks), ineligible=ineligible, time=stamp()))
    print(json.dumps(dict(status='PRODUCER_COMPLETE', points=points, tasks=len(queue))), flush=True)


if __name__ == '__main__': main()
