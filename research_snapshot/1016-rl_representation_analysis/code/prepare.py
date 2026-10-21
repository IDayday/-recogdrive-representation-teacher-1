"""Freeze train-only scene metadata and read-only cache/model identities."""
from common import *
import csv
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import shutil


def main():
    setup('prepare')
    source = ROOT.parent / '1010-il_baseline/manifests/cases.csv'
    rows = [r for r in csv.DictReader(source.open()) if r['cohort'] == 'navtrain']
    assert len(rows) == 103288 and len({r['token'] for r in rows}) == len(rows)
    assert all(r['domain'] == 'real' and r['partition'] in {'train', 'monitor'} for r in rows)
    fields = ['token', 'log_name', 'raw_path', 'frame_index', 'sensor_root', 'feature_dir', 'metric_cache', 'seed']
    rows = [dict({k: r[k] for k in fields if k != 'seed'}, seed=seed(r['token'])) for r in rows]
    rows.sort(key=lambda r: r['token'])
    dest = ROOT / 'manifests/navtrain.csv'
    if not dest.exists():
        tmp = dest.with_suffix('.csv.tmp')
        with tmp.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(dest)
    else:
        assert list(csv.DictReader(dest.open())) == [{k: str(v) for k, v in r.items()} for r in rows]
    def check(row):
        paths = [Path(row['metric_cache']), Path(row['raw_path'])]
        paths += [Path(row['feature_dir']) / n for n in ['complete.json', 'internvl_feature.gz', 'trajectory_target.gz']]
        return [str(p) for p in paths if not retry(p.is_file) or retry(p.stat).st_size <= 0]
    with ThreadPoolExecutor(max_workers=32) as pool:
        missing = [p for result in pool.map(check, rows) for p in result]
    assert not missing, missing[:20]
    cache_gate = read(ROOT.parent / '1008-il_synthetic/experiment/evidence/fresh_cache_gate.json')
    assert cache_gate['passed']
    repo = Path('/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive')
    vlm = repo / 'ReCogDrive-VLM-2B'
    for name, expected in cache_gate['vlm_sha256'].items():
        assert sha(vlm / name) == expected, name
    checkpoint = repo / 'ReCogDrive-2B-RL/ReCogDrive_Diffusion_Planner_2B_RL.ckpt'
    provenance = read(ROOT / 'provenance/source_snapshot.json')
    for row in provenance['files']:
        assert sha(ROOT / row['destination']) == row['sha256'], row['destination']
    scoring = dict(proposal_sampling=dict(num_poses=40, interval_length=.1),
                   scorer=dict(progress_weight=5., ttc_weight=5., comfortable_weight=2., driving_direction_weight=0.))
    protocol = dict(schema=1, model='ReCogDrive-2B-RL', checkpoint=str(checkpoint), checkpoint_sha256=sha(checkpoint),
                    vlm=str(vlm), vlm_sha256=cache_gate['vlm_sha256'],
                    cache_protocol_sha256=cache_gate['protocol_sha256'],
                    cache_policy_sha256=cache_gate['cache_policy_sha256'],
                    feature_cache_policy='read-only reuse of VLM features; all RL trajectories and scores newly generated',
                    cohort='navtrain', samples=len(rows), source_logs=len({r['log_name'] for r in rows}),
                    manifest_sha256=sha(dest), source_snapshot_sha256=sha(ROOT / 'provenance/source_snapshot.json'),
                    model_commit=provenance['model_commit'], root_seed=20261008, seed_index=0,
                    seed_formula='int(sha256(f"{token}|20261008|0".encode()).hexdigest()[:8],16)',
                    batch_size=1, planner_dtype='float32', autocast=False, mode='eval',
                    deterministic=False, grpo_training=False, cache_hidden_state=True,
                    sampling_method='ddim', denoising_steps=5, expected_timesteps=[80,60,40,20,0],
                    scoring=scoring, quality_thresholds=dict(failure_lt=.7, high_quality_gt=.9),
                    nodes=2, devices_per_node=16, total_ranks=32, no_navtest_access=True,
                    shared_reference_source=str(repo), monitor_interval_seconds=60)
    protocol['identity'] = digest(protocol)
    if (ROOT / 'configs/baseline.json').exists():
        assert read(ROOT / 'configs/baseline.json') == protocol
    else:
        atomic(ROOT / 'configs/baseline.json', protocol)
    evidence = dict(status='PASS', time=stamp(), samples=len(rows), missing=missing,
                    model_checkpoint_sha256=protocol['checkpoint_sha256'], manifest_sha256=protocol['manifest_sha256'],
                    source_snapshot_sha256=protocol['source_snapshot_sha256'],
                    versions={n: importlib.metadata.version(n) for n in ['torch','torchvision','transformers','diffusers','numpy','scipy','nuplan-devkit','timm']},
                    note='No prior IL/RL scores or test caches are loaded; train-only metadata and frozen VLM feature caches reused.')
    atomic(ROOT / 'provenance/assets_prepared.json', evidence)
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
