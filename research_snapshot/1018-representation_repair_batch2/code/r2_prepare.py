"""Freeze training-only source identities and the initial six-node execution matrix."""
from r2_common import *
import collections


def main():
    setup('prepare')
    import numpy as np
    rows_path = OLD / 'manifests/natural_s0.json'
    rows = read(rows_path)
    scores_path = OLD / 'analysis/natural_route1_v1/scores.npy'
    quality = np.load(scores_path, mmap_mode='r')
    assert len(rows) == len(quality) == 103288
    assert all(r['cohort'] != 'navtest' for r in rows if 'cohort' in r)
    cells = []
    for node in [0, 1]:
        for item in read(OLD / f'vlm_repair_v1/CACHE_NODE{node}.json')['cells']:
            if item['group'] in ['command', 'requirements']: continue
            cells.append(dict(item, absolute_path=str(OLD / item['path']),
                              proof_path=str(OLD / 'vlm_repair_v1/cells' / (item['cell'] + '.json'))))
    semantic = read(OLD / 'vlm_semantic_v2/CACHE_ACCEPTANCE.json')
    for check in semantic['cell_checks']:
        proof = OLD / 'vlm_semantic_v2/cells' / (check['cell'] + '.json')
        item = read(proof)
        cells.append(dict(item, absolute_path=str(OLD / item['path']), proof_path=str(proof)))
    assert len({c['cell'] for c in cells}) == len(cells)
    blocks = sorted({c['block'] for c in cells})
    assert len(blocks) == 62
    for item in cells:
        path = Path(item['absolute_path'])
        assert path.is_file()
        array = np.load(path, mmap_mode='r')
        assert list(array.shape) == item['shape'] and array.shape[0] == len(rows)
        item['dtype'] = str(array.dtype)
        item['bytes'] = path.stat().st_size
    cells.sort(key=lambda c: (c['block'], c['group']))
    atomic(ROOT / 'manifests/cells.json', cells)
    exploration = np.array([r['subset'] == 'exploration' for r in rows])
    fold = np.array([int(digest({'session': r['session'], 'cv_root': 20261016})[:8], 16) % 5 for r in rows])
    atomic(ROOT / 'manifests/data_source.json', {'rows': str(rows_path), 'rows_sha256': sha(rows_path),
           'quality': str(scores_path), 'quality_sha256': sha(scores_path),
           'cases': len(rows), 'exploration': int(exploration.sum()), 'validation': int((~exploration).sum()),
           'exploration_failure': int((exploration & (quality < .7)).sum()),
           'exploration_high': int((exploration & (quality > .9)).sum()),
           'cv_folds': 5, 'cv_formula': 'sha256 canonical JSON {session,cv_root:20261016}, first8 mod5',
           'split_reused_from_batch1': True, 'test_opened': False})
    atomic(ROOT / 'config/execution_v1.json', {'status': 'FROZEN_INITIAL_EXECUTION', 'time': stamp(),
           'maximum_runtime_minutes': 4320, 'target_node_count': 6, 'target_cards_per_node': 16,
           'approximate_compute_window_hours': 30, 'nodes_and_devices_configurable': True,
           'nonzero_K': list(range(2, 9)),
           'initialization_families': ['representation_multiview', 'actual_intervention_response', 'bounded_case_correction'],
           'fit_seeds': [2026101801, 2026101802, 2026101803], 'system_initial_starts_target': 63,
           'router_families': ['hard_with_intensity', 'joint_soft_delta', 'independent_trajectory_selector'],
           'development_sampling_indices': [0, 1, 2], 'final_sampling_indices': [0, 1, 2, 3, 4],
           'candidate_selection': ['safety', 'PDMS'], 'identity_expert': True,
           'minimum_effective_group_cases': 24, 'minimum_group_sessions': 4,
           'rank_safeguard': 'numerical rank and subgroup support, report all clipped/ineligible dimensions',
           'screening': 'all components/layers and cached token pools, hierarchical budgets; actual gains drive expert selection',
           'budget_fraction': {'expert_discovery': .4, 'routing': .25, 'validation_test': .25, 'diagnostic_and_buffer': .1},
           'no_new_K1_training': True, 'no_test_based_fitting': True, 'automatic_release': False})
    anchors = read(OLD / 'repair_v1/anchors.json')[:2]
    by_token = {r['token']: r for r in rows}
    atomic(ROOT / 'manifests/anchors.json', [dict(by_token[a['token']], **a) for a in anchors])
    atomic(ROOT / 'provenance/ASSET_PRECHECK.json', {'status': 'PASS_METADATA', 'time': stamp(),
           'cells': len(cells), 'blocks': blocks, 'valid_cells': sum(c.get('valid_cases', 1) > 0 for c in cells),
           'source_bytes': sum(c['bytes'] for c in cells), 'per_case_cache_available': True,
           'full_source_hashes_pending_distributed_audit': True, 'model_checkpoint': read(OLD / 'configs/baseline.json')['checkpoint'],
           'first_batch_unchanged': True, 'test_accessed': False})
    nodes = [('peer_a1', 'dlcb46akrk2hji1u'), ('peer_a2', 'dlcgxxrm3yape59d'),
             ('peer_b1', 'dlcqdtslnqnytsc7'), ('peer_b2', 'dlcwhkv0rt5t8crx'),
             ('self_0', 'dlcrnshl7t4hcmoy'), ('self_1', 'dlcrxs2yz4ime2fe')]
    atomic(ROOT / 'resources/NODES.json', {'time': stamp(), 'nodes': [
           {'name': n, 'job': j, 'devices': list(range(16)), 'rank_base': i * 16,
            'cpu_workers_after_smoke': 24, 'cpu_threads': 2} for i, (n, j) in enumerate(nodes)]})
    if not (RUN / 'tasks_cpu.json').exists(): append('cpu', [])
    if not (RUN / 'tasks_gpu.json').exists(): append('gpu', [])
    print(json.dumps({'status': 'PASS_METADATA', 'cells': len(cells), 'blocks': len(blocks),
                      'exploration': int(exploration.sum()), 'sources_bytes': sum(c['bytes'] for c in cells)}))


if __name__ == '__main__': main()
