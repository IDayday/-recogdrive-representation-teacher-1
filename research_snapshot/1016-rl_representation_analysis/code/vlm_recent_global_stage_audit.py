"""Read-only audit of genuinely recent committed results from all 32 ranks."""
from common import *
import numpy as np
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/recent_stage_audit')
    base = ROOT/'runs/vlm_global_refine_20261016_v5'
    paths = sorted((base/'receipts').glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    latest = {}
    for p in paths:
        proof = read(p)
        latest.setdefault(proof['rank'], (p, proof))
        if len(latest) == 32:
            break
    assert set(latest) == set(range(32))
    original = ROOT/'candidate_repair_v1/analysis/navtrain_full_locked'
    scores = np.load(original/'scores.npy', mmap_mode='r')
    positions = {r['token']: i for i, r in enumerate(read(original/'rows.json'))}
    fields = ['score', *COMPONENTS]
    checks = []
    for rank, (receipt, proof) in sorted(latest.items()):
        path = base/'results'/receipt.name
        assert sha(path) == proof['result_sha256']
        value = read(path)
        stage = base/'stages'/value['task']['stage']
        arms = {a['id']: a for a in read(stage/'arms.json')}
        baseline = {}
        for r in value['records']:
            assert r['seed'] == seed(r['token'], r['seed_index'])
            assert r['quality'] == quality(r['score']['score'])
            trajectory = np.asarray(r['trajectory'])
            assert trajectory.shape == (8, 3) and np.isfinite(trajectory).all()
            assert all(np.isfinite(v) and 0 <= v <= 1+1e-8 for v in r['score'].values())
            assert r['edit']['relative_edit_max'] <= arms.get(r['arm'], {}).get('cap', 0)+1e-6
            if r['arm'] == 'baseline':
                target = scores[r['seed_index'], positions[r['token']], 0]
                assert np.array_equal([r['score'][f] for f in fields], target)
                baseline[r['token'], r['seed_index']] = r
        assert baseline
        assert all((r['token'], r['seed_index']) in baseline for r in value['records'])
        checks.append(dict(rank=rank, receipt_time=proof['time'], task=value['task'],
                           result_sha256=proof['result_sha256'], records=len(value['records'])))
    out = VOUT/'audits'/('recent_global_stage_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(out, dict(status='PASS', time=stamp(), cards=32, checks=checks,
                     records=sum(r['records'] for r in checks), newest_receipt_selected_by_mtime=True,
                     baseline_all_seven_fields_exact_previous_full_training=True,
                     seeds_shape_scores_quality_caps_checked=True,
                     code_sha256=sha(Path(__file__))))
    print('RECENT_GLOBAL_ALL_32_STAGE_AUDIT_PASS', str(out.relative_to(ROOT)), flush=True)


if __name__ == '__main__':
    main()
