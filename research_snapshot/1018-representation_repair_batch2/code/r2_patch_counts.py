"""Recover exact per-scene image tiling from already audited cached masks."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')};valid=[];sources=[]
    for tile in range(13):
        c=cells[f'vision_23__tile_{tile:02d}'];x=np.load(c['absolute_path'],mmap_mode='r')
        valid.append(np.isfinite(x[:,0]));sources.append(dict(cell=c['cell'],sha256=c['sha256']))
    valid=np.stack(valid,1);counts=valid.sum(1)
    assert np.all((counts>=1)&(counts<=13)) and np.array_equal(valid,np.arange(13)[None,:]<counts[:,None])
    target=ROOT/'manifests/patch_counts.npz';hashed=save_npz(target,counts=counts.astype('int16'))
    result=dict(status='PASS',time=stamp(),path=str(target.relative_to(ROOT)),sha256=hashed,rows=len(counts),
                histogram={str(int(n)):int(np.sum(counts==n)) for n in np.unique(counts)},sources=sources,
                no_model_recollection=True,contiguous_valid_tiles_checked=True)
    atomic(ROOT/'manifests/PATCH_COUNTS.json',result);return result
