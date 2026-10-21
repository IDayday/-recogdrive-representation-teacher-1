"""Batch-two paths, private environment, append-only tasks and atomic outputs."""
from __future__ import annotations
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / '1016-rl_representation_analysis'
RUN = ROOT / 'runs/discovery_v1'


def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()


def retry(function):
    for attempt in range(6):
        try: return function()
        except OSError as error:
            if error.errno not in {errno.ESTALE, errno.EIO, errno.ETIMEDOUT, errno.EAGAIN} or attempt == 5: raise
            time.sleep(min(.25 * 2 ** attempt, 4))


def read(path): return retry(lambda: json.loads(Path(path).read_text()))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    def calculate():
        h = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
        return h.hexdigest()
    return retry(calculate)


def atomic(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(ROOT), path
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    def write():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(data); temporary.replace(path)
    retry(write)


def setup(name, threads=1):
    base = ROOT / 'runtime' / name
    base.mkdir(parents=True, exist_ok=True)
    for key in ['HF_HOME', 'HF_MODULES_CACHE', 'TRANSFORMERS_CACHE', 'TORCH_HOME', 'XDG_CACHE_HOME',
                'MPLCONFIGDIR', 'NUMBA_CACHE_DIR', 'TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR',
                'TORCH_EXTENSIONS_DIR', 'TMPDIR']:
        path = base / key.lower(); path.mkdir(exist_ok=True); os.environ[key] = str(path)
    for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        os.environ[key] = str(threads)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      TOKENIZERS_PARALLELISM='false', NUPLAN_MAPS_ROOT='/mnt/data/navsim/maps',
                      NUPLAN_MAP_VERSION='nuplan-maps-v1.0')
    sys.dont_write_bytecode = True
    for path in [OLD / 'code/upstream', OLD / 'deps', OLD / 'code', ROOT / 'code']:
        if str(path) not in sys.path: sys.path.insert(0, str(path))


def compatibility():
    import numpy as np
    if int(np.__version__.split('.')[0]) < 2:
        sys.modules.setdefault('numpy._core.numeric', np.core.numeric)


def seed(token, j=0):
    return int(hashlib.sha256(f'{token}|20261008|{j}'.encode()).hexdigest()[:8], 16)


def append(kind, tasks):
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / f'{kind}.lock').open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        path = RUN / f'tasks_{kind}.json'
        previous = read(path) if path.exists() else []
        existing = {x['id'] for x in previous}
        assert not existing.intersection(x['id'] for x in tasks)
        atomic(path, previous + tasks)


def claim(kind, worker):
    path = RUN / f'tasks_{kind}.json'
    if not path.exists(): return None
    for task in read(path):
        if (RUN / f'receipts_{kind}' / (task['id'] + '.json')).exists(): continue
        folder = RUN / f'claims_{kind}' / task['id']
        folder.parent.mkdir(parents=True, exist_ok=True)
        try: folder.mkdir()
        except FileExistsError: continue
        atomic(folder / 'OWNER.json', {'worker': worker, 'hostname': socket.gethostname(),
               'pid': os.getpid(), 'time': stamp(), 'task': task})
        return task
    return None
