"""Fold-contained multiview failure initialization; no semantic failure classes."""
from r2_common import *


def run(task):
    import numpy as np
    from scipy.special import softmax
    from sklearn.cluster import KMeans
    from sklearn.utils.extmath import randomized_svd
    source = read(ROOT / 'manifests/data_source.json')
    rows = read(source['rows']); quality = np.load(source['quality'])
    exploration = np.array([r['subset'] == 'exploration' for r in rows])
    folds = np.array([int(digest({'session': r['session'], 'cv_root': 20261016})[:8], 16) % 5 for r in rows])
    held = task['heldout_fold']
    train = exploration & ((folds != held) if held >= 0 else True)
    failures = np.flatnonzero(train & (quality < .7))
    high = np.flatnonzero(train & (quality > .9))
    high = np.array(sorted(high, key=lambda i: digest({'token': rows[i]['token'], 'initial_high': 20261018}))[:8192])
    index = {c['cell']: c for c in read(ROOT / 'manifests/cells.json')}
    views = ['vision_23__patch_mean', 'bridge_3__patch_mean', 'language_07__valid_mean',
             'language_15__valid_mean', 'interface_pre__valid_mean', 'interface_post__valid_mean']
    encodings = []; transforms = {}
    for name in views:
        cell = index[name]; x = np.load(cell['absolute_path'], mmap_mode='r')
        assert np.isfinite(x[failures]).all()
        success = np.asarray(x[high], dtype=np.float64)
        mean = success.mean(0); scale = np.maximum(success.std(0), 1e-6)
        failed = (np.asarray(x[failures], dtype=np.float64)-mean) / scale
        n = min(16, min(failed.shape)-1)
        _, _, v = randomized_svd(failed, n_components=n, random_state=20261018)
        z = failed @ v.T; zs = np.maximum(z.std(0), 1e-6)
        encodings.append(z/zs/np.sqrt(n))
        transforms[name+'_mean'] = mean.astype('float32')
        transforms[name+'_scale'] = scale.astype('float32')
        transforms[name+'_basis'] = v.T.astype('float32')
        transforms[name+'_projection_scale'] = zs.astype('float32')
    features = np.concatenate(encodings, 1)
    folder = ROOT / 'analysis/initial_groups' / ('all' if held < 0 else f'fold{held}')
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'representation_features.npz').open('wb') as stream:
        np.savez(stream, global_indices=failures, features=features.astype('float32'), **transforms)
    records = []
    for k in range(2, 9):
        for replicate, value in enumerate(read(ROOT/'config/execution_v1.json')['fit_seeds']):
            model = KMeans(n_clusters=k, random_state=value, n_init=5).fit(features)
            distances = model.transform(features)**2
            temperature = max(float(np.median(np.min(distances, 1))) * .25, 1e-5)
            responsibilities = softmax(-distances/temperature, axis=1)
            ident = f'representation_K{k}_seed{replicate}'
            target = folder/(ident+'.npz')
            with target.open('wb') as stream:
                np.savez(stream, global_indices=failures, responsibility=responsibilities.astype('float32'),
                         centers=model.cluster_centers_.astype('float32'), temperature=temperature)
            counts = np.bincount(model.labels_, minlength=k)
            sessions = [len({rows[i]['session'] for i in failures[model.labels_==e]}) for e in range(k)]
            ess = responsibilities.sum(0)**2/np.maximum(np.square(responsibilities).sum(0),1e-12)
            record = dict(id=ident, K=k, fit_seed=value, heldout_fold=held, path=str(target.relative_to(ROOT)),
                          sha256=sha(target), hard_counts=counts.tolist(), sessions=sessions,
                          effective_counts=ess.tolist(), train_cases=len(failures),
                          family='representation_multiview', fit_only_training_fold=True)
            atomic(target.with_suffix('.json'), record); records.append(record)
    atomic(folder/'COMPLETE.json', dict(status='PASS',time=stamp(),family='representation_multiview',
           heldout_fold=held, train_failures=len(failures), high_reference_samples=len(high),
           source_views=views, initialization_systems=records, no_validation_or_test_fitted=True))
    return dict(path=str((folder/'COMPLETE.json').relative_to(ROOT)), systems=len(records))
