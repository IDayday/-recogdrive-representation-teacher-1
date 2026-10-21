"""Task-local paths, reproducible per-scene seeds, and bounded storage retries."""
from __future__ import annotations
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'code/upstream'
sys.dont_write_bytecode = True
COMPONENTS = ['no_at_fault_collisions', 'drivable_area_compliance', 'ego_progress',
              'time_to_collision_within_bound', 'comfort', 'driving_direction_compliance']


def retry(function):
    for attempt in range(6):
        try:
            return function()
        except OSError as error:
            if error.errno not in {errno.ESTALE, errno.EIO, errno.ETIMEDOUT, errno.EAGAIN} or attempt == 5:
                raise
            time.sleep(min(.25 * 2 ** attempt, 4))


def read(path):
    return retry(lambda: json.loads(Path(path).read_text()))


def sha(path):
    def run():
        h = hashlib.sha256()
        with open(path, 'rb') as stream:
            for chunk in iter(lambda: stream.read(8 << 20), b''):
                h.update(chunk)
        return h.hexdigest()
    return retry(run)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(ROOT), path
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    def run():
        tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
        tmp.write_text(data)
        tmp.replace(path)
    retry(run)


def setup(name):
    base = ROOT / 'runtime' / name
    base.mkdir(parents=True, exist_ok=True)
    for key in ['HF_HOME', 'HF_MODULES_CACHE', 'TRANSFORMERS_CACHE', 'TORCH_HOME', 'XDG_CACHE_HOME',
                'MPLCONFIGDIR', 'NUMBA_CACHE_DIR', 'TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR',
                'TORCH_EXTENSIONS_DIR', 'TMPDIR']:
        value = base / key.lower()
        value.mkdir(exist_ok=True)
        os.environ[key] = str(value)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      TOKENIZERS_PARALLELISM='false', NUPLAN_MAPS_ROOT='/mnt/data/navsim/maps',
                      NUPLAN_MAP_VERSION='nuplan-maps-v1.0', OMP_NUM_THREADS='1',
                      MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    sys.path.insert(0, str(UPSTREAM))
    if (ROOT / 'deps').exists():
        sys.path.insert(0, str(ROOT / 'deps'))


def seed(token, j=0):
    return int(hashlib.sha256(f'{token}|20261008|{j}'.encode('utf-8')).hexdigest()[:8], 16)


def reseed(value):
    import numpy as np
    import torch
    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)
    torch.cuda.manual_seed_all(value)


def compatibility():
    import numpy as np
    if int(np.__version__.split('.')[0]) < 2:
        sys.modules.setdefault('numpy._core.numeric', np.core.numeric)


def quality(value):
    return 'failure' if value < .7 else 'high_quality' if value > .9 else 'intermediate'
