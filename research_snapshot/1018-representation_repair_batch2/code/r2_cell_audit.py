"""Full cached-array identity audit; no model collection or quality re-selection."""
from r2_common import *


def run(task):
    import numpy as np
    cell = task['cell']; path = Path(cell['absolute_path'])
    assert sha(path) == cell['sha256']
    array = np.load(path, mmap_mode='r')
    assert list(array.shape) == cell['shape']
    finite = np.isfinite(array[:, 0])
    expected = cell.get('valid_cases')
    if expected is not None: assert int(finite.sum()) == expected
    destination = ROOT / 'provenance/cells' / (cell['cell'] + '.json')
    result = dict(status='PASS', time=stamp(), cell=cell['cell'], source_sha256=cell['sha256'],
                  shape=list(array.shape), valid_cases=int(finite.sum()),
                  dtype=str(array.dtype), model_recollected=False)
    atomic(destination, result)
    return dict(path=str(destination.relative_to(ROOT)), sha256=sha(destination))
