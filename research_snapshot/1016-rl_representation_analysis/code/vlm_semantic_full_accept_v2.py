"""Audit all corrected-span CV outputs before interpreting their candidate pool."""
from common import *
import numpy as np
from vlm_semantic import SEM
from vlm_scan import metadata
from vlm_space import METRICS
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_semantic_v2/full_accept')
    assert read(SEM/'CACHE_ACCEPTANCE.json')['status'] == 'PASS'
    rows, q, exp, fold, sessions, high = metadata()
    assert not set(sessions[exp]) & set(sessions[~exp])
    checks = []
    for kind, workers in [('rapid', 16), ('scan', 64)]:
        base = SEM/kind
        tasks = read(base/'tasks.json')
        assert len(tasks) == len(list((base/'receipts').glob('*.json'))) == 64
        entries = read(base/'CONFIGS.json')
        assert len(entries) == (81 if kind == 'rapid' else 11633)
        expected = set(range(16))
        if kind == 'scan':
            for node in [0, 1]:
                for auxiliary in ['cpu_extra', 'cpu_wave']:
                    expected.update(read(SEM/auxiliary/f'node{node}/PREFLIGHT.json')['ranks'])
        assert len(expected) == workers
        actual = {int(p.stem[4:]) for p in (base/'smoke').glob('rank*.json')}
        assert actual == expected, (kind, sorted(actual), sorted(expected))
        assert all(read(base/'smoke'/f'rank{r:03d}.json')['status'] == 'PASS' for r in expected)
        for task in tasks:
            name = task['id']+'.json'
            receipt = read(base/'receipts'/name)
            path = base/'results'/name
            assert sha(path) == receipt['result_sha256']
            result = read(path)
            source = read(SEM/'cells'/name)
            assert result['source_sha256'] == source['sha256']
            if result['status'] == 'INELIGIBLE':
                assert task['cell'] == 'language_input__requirements_v2'
                checks.append(dict(kind=kind, cell=task['cell'], status='INELIGIBLE', result_sha256=sha(path)))
                continue
            assert result['status'] == 'COMPLETE'
            assert result['training_class_sizes'] == [74900, 1850]
            assert not result['test_accessed'] and not result['heldout_validation_evaluated']
            assert result['metric_fields'] == METRICS
            for item in ['array', 'moment']:
                assert sha(ROOT/result[item+'_path']) == result[item+'_sha256']
            with np.load(ROOT/result['array_path']) as z:
                assert z['metrics'].shape == (2, 6, len(entries), len(METRICS))
                indices = z['evaluation_indices']
                assert exp[indices].all() and ((q[indices] < .7) | (q[indices] > .9)).all()
                assert len(np.unique(indices)) == len(indices)
                assert np.array_equal(z['fold_ids'], fold[indices])
                assert int((q[indices] > .9).sum()) <= 8192
                for metric in [0, 1, 8]:
                    values = z['metrics'][:, :, :, metric]
                    values = values[np.isfinite(values)]
                    assert ((values >= -1e-10) & (values <= 1+1e-10)).all()
                if kind == 'scan':
                    d = result['dimension']
                    bounds = np.array([min(c['kf'], max(0, d-c['ks'])) if c['kind'].endswith('residual') else 65535 for c in entries])
                    assert not (z['ranks'][:, :, :, 2] > bounds[None, None]).any()
                    eligible = (z['status'] == 0).all(1) & ~z['cutoff_degenerate'].any(1)
                    requested = np.array([c['r'] or 0 for c in entries])
                    assert not (eligible & (requested[None] > bounds[None])).any()
            checks.append(dict(kind=kind, cell=task['cell'], status='COMPLETE', result_sha256=sha(path),
                               array_sha256=result['array_sha256'], moment_sha256=result['moment_sha256']))
    assert sum(r['status'] == 'INELIGIBLE' for r in checks) == 2
    out = SEM/'audits'/('full_cv_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(out, dict(status='PASS', time=stamp(), checks=checks, source_cases=len(rows),
                     session_splits_disjoint=True, training_classes_full_statistics=True,
                     all_corrected_full_and_rapid_cells_complete=True, no_test_or_intervention_claim=True,
                     code_sha256=sha(Path(__file__))))
    atomic(SEM/'FULL_ANALYSIS_ACCEPTANCE_LATEST.json', dict(path=str(out.relative_to(ROOT)), sha256=sha(out)))
    print('CORRECTED_FULL_CV_ACCEPTANCE_PASS', len(checks), str(out.relative_to(ROOT)), flush=True)


if __name__ == '__main__':
    main()
