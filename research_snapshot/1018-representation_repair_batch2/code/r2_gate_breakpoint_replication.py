"""Replicate the declared pre-all calibration signal on the other whole fits.

Only existing canonical predictions get priority; immutable CPU calibration and
real-score replay remain unchanged. Never select a fit from held outcomes.
"""
from r2_common import *
from r2_resume_support import append_once, register_once, enqueue


def main():
    setup('gate_breakpoint_replication')
    path = ROOT/'config/GATE_BREAKPOINT_REPLICATION_PROTOCOL_V1.json'
    protocol = read(path); protocol_hash = sha(path)
    original = 'config/GATE_BREAKPOINT_CONTROL_PROTOCOL_V1.json'
    handler = 'code/r2_gate_breakpoint_control.py'
    assert sha(ROOT/handler) == read(ROOT/'provenance/GATE_BREAKPOINT_ENGINEERING_PASS.json')['source_sha256']
    targets = {(s, h, r) for s in protocol['systems'] for h in range(5) for r in ['PDMS', 'safety']}
    states = {}; cached = {}; published = set()
    for name in protocol['canonical_sources']:
        base = ROOT/'runs/gate_breakpoint_replication_frontier_v1'/Path(name).name
        if not (base/'tasks.json').exists():
            atomic(base/'tasks.json', [])
            atomic(base/'producer.json', dict(complete=False, tasks=0, time=stamp()))
        register_once(dict(name='gate_replication_'+base.name, path=str(base.relative_to(ROOT)),
            handler='code/r2_scientific_admission.py', handler_sha256=sha(ROOT/'code/r2_scientific_admission.py'),
            kind='custom', priority=24.05, enabled=False))
        queue = read(base/'tasks.json')
        states[name] = dict(base=base, queue=queue, known={t['id'] for t in queue},
            pending={t['id']:t for t in queue if not (base/'receipts'/(t['id']+'.json')).exists()})
    while True:
        assert sha(path) == protocol_hash
        registry = read(ROOT/'config/GPU_STAGES.json')['stages']; report = {}
        for name, state in states.items():
            source = ROOT/name; manifest = source/'tasks.json'
            if not manifest.exists(): continue
            version = manifest.stat().st_mtime_ns
            if cached.get(name, (None, None))[0] != version:
                points = {}; selected = []
                for t in read(manifest):
                    point = t['point']
                    if point not in points: points[point] = read(ROOT/point)
                    d = points[point]
                    if (d.get('system'), d.get('heldout_fold'), d.get('role')) in targets and d.get('wave') == 1:
                        selected.append(t)
                selected.sort(key=lambda t:(t['point'], t.get('start', 0), t['id']))
                cached[name] = (version, selected)
            done = {p.stem for p in (source/'receipts').glob('*.json')}
            claimed = {p.name for p in (source/'claims').glob('*')}
            for ident, t in list(state['pending'].items()):
                if (state['base']/'receipts'/(ident+'.json')).exists() or t['canonical_task']['id'] in done:
                    state['pending'].pop(ident)
            stage = min((s for s in registry if s['path'] == name), key=lambda s:s['priority'])
            added = 0
            for t in cached[name][1]:
                if len(state['pending']) >= protocol['maximum_outstanding_per_source']: break
                ident = 'gate_replication_frontier_'+digest(dict(stage=name, id=t['id']))[:24]
                if ident in state['known'] or t['id'] in done or t['id'] in claimed: continue
                carrier = dict(id=ident, canonical_stage=name, canonical_task=t,
                    scientific_handler={k:stage[k] for k in ['handler','handler_sha256','kind']})
                enqueue(state['queue'], state['known'], carrier); state['pending'][ident] = carrier; added += 1
            if added:
                atomic(state['base']/'tasks.json', state['queue'])
                atomic(state['base']/'producer.json', dict(complete=False, tasks=len(state['queue']), time=stamp()))
            report[name] = dict(selected=len(cached[name][1]), completed=sum(t['id'] in done for t in cached[name][1]),
                outstanding=len(state['pending']), added=added)
        assessments = {}
        for p in (ROOT/'analysis/context_token_policy_cv/pre_all').glob('*.json'):
            d = read(p); key = (d.get('system'), d.get('heldout_fold'), d.get('role'))
            if key not in targets or d.get('wave') != 1: continue
            assert key not in assessments and d['heldout_outcomes_not_used_to_route']
            assert not d['validation_accessed'] and not d['test_accessed']
            assessments[key] = (p, d)
        tasks = []
        for key, (p, d) in sorted(assessments.items()):
            ident = 'outcome_gate_breakpoint_rep_'+digest(dict(policy=d['policy'], protocol=protocol_hash))[:24]
            t = dict(id=ident, policy=d['policy'], policy_sha256=sha(ROOT/d['policy']),
                assessment=str(p.relative_to(ROOT)), assessment_sha256=sha(p), view='pre_all',
                system=key[0], heldout_fold=key[1], role=key[2], fit_seed=d['fit_seed'],
                protocol=original, protocol_sha256=sha(ROOT/original), handler=handler, handler_sha256=sha(ROOT/handler))
            tasks.append(t)
        done_cpu = [t for t in tasks if (RUN/'receipts_cpu'/(t['id']+'.json')).exists()]
        failed = [t['id'] for t in tasks if (RUN/'failures_cpu'/(t['id']+'.json')).exists()]
        if failed:
            atomic(ROOT/'analysis/gate_breakpoint_replication/ATTENTION.json', dict(time=stamp(), failed=failed))
            return
        active = published-{t['id'] for t in done_cpu}; new = []
        for t in tasks:
            if len(active)+len(new) >= 8: break
            if t['id'] not in published and t not in done_cpu: new.append(t); published.add(t['id'])
        if new: append_once('cpu', new)
        atomic(ROOT/'analysis/gate_breakpoint_replication/TASK_LINEAGE.json', dict(time=stamp(), tasks=tasks))
        pointer = read(ROOT/'analysis/extended_cv_reviews/LATEST.json'); review = read(ROOT/pointer['path'])
        methods = {f'token_breakpoint_pre_all_{v}_wave1' for v in read(ROOT/original)['variants']}
        full = [r for r in review['recipes'] if r['system'] in protocol['systems'] and r['method'] in methods and r['complete_five_folds']]
        atomic(ROOT/'analysis/gate_breakpoint_replication/LIVE.json', dict(time=stamp(), sources=report,
            assessments=len(assessments), expected_CPU_tasks=len(targets), CPU_completed=len(done_cpu),
            whole_fivefold_recipes=len(full), expected_recipes=8, no_new_model_or_trajectory_or_score=True))
        if len(done_cpu) == len(targets) and len(full) == 8:
            atomic(ROOT/'analysis/gate_breakpoint_replication/COMPLETE.json', dict(time=stamp(), status='ALL_MATCHED_SECOND_AND_THIRD_FIT_CONTROLS_READY',
                snapshot=pointer, recipes=full, all_fits_reported_not_selected=True))
            return
        time.sleep(30)


if __name__ == '__main__': main()
