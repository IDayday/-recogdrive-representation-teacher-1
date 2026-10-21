"""Paired HT-minus-T (or another fixed pair) without selecting on test scores."""
import argparse
import numpy as np
from continuation.layout import write_json
from continuation.summarize import read_complete, paired_scores, session_interval


def main(a):
    left_id, left = read_complete(a.left); right_id, right = read_complete(a.right)
    for key in ['cohort', 'noises', 'subset', 'development', 'limit', 'environment']:
        if left_id.get(key) != right_id.get(key):
            raise ValueError('Evaluation scopes or environments differ: ' + key)
    left = {v['token']: v for v in left}; right = {v['token']: v for v in right}
    if left.keys() != right.keys():
        raise ValueError('Paired evaluations must cover the same scenes')
    delta = []; sessions = []; pools = []
    for token, row in left.items():
        other = right[token]
        if any(row.get(k) != other.get(k) for k in ['session', 'subset', 'pool']):
            raise ValueError('Paired scene identity differs')
        base, actual = paired_scores(row, left_id); other_base, other_actual = paired_scores(other, right_id)
        if base != other_base:
            raise ValueError('Paired evaluations have different matched Base scores')
        delta.append(float(np.mean([x['score'] - y['score'] for x, y in zip(actual, other_actual)]) * 100))
        sessions.append(row['session']); pools.append(row.get('pool', 'unknown'))
    def panel(indices):
        return dict(cases=len(indices), gain=float(np.mean([delta[i] for i in indices])),
            session_bootstrap_gain_CI95=session_interval([delta[i] for i in indices], [sessions[i] for i in indices]))
    result = dict(status='PASS_PAIRED_FIXED_MODEL_COMPARISON', left_identity=left_id, right_identity=right_id,
        **panel(list(range(len(delta)))), by_pool={p: panel([i for i, value in enumerate(pools) if value == p]) for p in sorted(set(pools))},
        independent_training_repeats=1, multiple_noise_draws_are_not_independent_training_repeats=True)
    write_json(a.out, result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--left', required=True); p.add_argument('--right', required=True)
    p.add_argument('--out', required=True); main(p.parse_args())
