"""Scene-level matched scores and session bootstrap; draws are not independent trials."""
import argparse
import json
from pathlib import Path
import numpy as np
from continuation.layout import write_json

SAFETY = ['no_at_fault_collisions', 'drivable_area_compliance', 'time_to_collision_within_bound']

def session_interval(values, sessions, seed=2026102201, repeats=2000):
    names = sorted(set(sessions)); index = {name: i for i, name in enumerate(names)}
    if not names or len(values) != len(sessions):
        raise ValueError('Nonempty paired values/sessions required')
    sums = np.zeros(len(names)); counts = np.zeros(len(names))
    for value, name in zip(values, sessions):
        sums[index[name]] += value; counts[index[name]] += 1
    rng = np.random.default_rng(seed); draw = rng.integers(0, len(names), size=(repeats, len(names)))
    estimates = sums[draw].sum(1) / counts[draw].sum(1)
    return np.quantile(estimates, [.025, .975]).tolist()

def paired_scores(record, identity):
    expected = [int(v) for v in identity['noises'].split(',')]
    arrays = []
    for kind in ['Base', 'student']:
        rows = [v for v in record['records'] if v['kind'] == kind]
        if [v['seed_index'] for v in rows] != expected:
            raise ValueError('Incomplete or reordered noise pairing')
        arrays.append([v['score'] for v in rows])
    if len(record['records']) != 2 * len(expected):
        raise ValueError('Unexpected evaluation draws')
    return arrays

def read_complete(root):
    root = Path(root); identity = json.loads((root / 'FROZEN_MODEL.json').read_text())
    records = []; seen = set()
    for path in sorted((root / 'cases').glob('*.json')):
        record = json.loads(path.read_text())
        if record['identity'] != identity or record['token'] in seen:
            raise ValueError('Mixed/duplicate evaluation identity')
        paired_scores(record, identity); seen.add(record['token']); records.append(record)
    completed = [json.loads(p.read_text()) for p in root.glob('COMPLETE_rank*.json')]
    if not completed:
        raise ValueError('Missing shard completion receipts')
    world = completed[0]['world_size']
    if len(completed) != world or {v['rank'] for v in completed} != set(range(world)) or any(
        v['world_size'] != world or v['identity'] != identity or
        v['status'] != 'COMPLETE_TARGET_BACKEND_EVALUATION_SHARD' for v in completed):
        raise ValueError('Not all evaluation ranks completed with the same identity')
    if sum(v['cases'] for v in completed) != len(records) or not records:
        raise ValueError('Evaluation coverage differs from the completed shards')
    return identity, records

def aggregate(records, identity):
    pairs = [paired_scores(v, identity) for v in records]
    b = np.asarray([[v['score'] for v in base] for base, _ in pairs])
    q = np.asarray([[v['score'] for v in student] for _, student in pairs])
    delta = (q - b).mean(1) * 100; safety = {}
    for name in SAFETY:
        bv = np.asarray([[v[name] for v in base] for base, _ in pairs])
        qv = np.asarray([[v[name] for v in student] for _, student in pairs])
        safety[name] = dict(new=int(((qv < 1) & (bv >= 1)).sum()), removed=int(((qv >= 1) & (bv < 1)).sum()))
    return dict(cases=len(records), sessions=len(set(x['session'] for x in records)),
        Base_PDMS=float(b.mean() * 100), student_PDMS=float(q.mean() * 100), gain=float(delta.mean()),
        session_bootstrap_gain_CI95=session_interval(delta, [v['session'] for v in records]),
        safety_events=safety, Base_over_90_scenes=int((b.mean(1) > .9).sum()),
        Base_over_90_harmed_scenes=int(((b.mean(1) > .9) & (delta < 0)).sum()))

def main(a):
    root = Path(a.input); identity, records = read_complete(root)
    panels = {}
    for field in ['subset', 'pool']:
        panels[field] = {label: aggregate([v for v in records if v.get(field) == label], identity)
            for label in sorted({v[field] for v in records if field in v})}
    summary = dict(status='PASS_COMPLETE_MATCHED_TARGET_EVALUATION', identity=identity,
        **aggregate(records, identity), panels=panels, independent_training_repeats=1,
        source_PPU_results_not_substituted=True)
    write_json(root / 'SUMMARY.json', summary); print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--input', required=True); main(p.parse_args())
