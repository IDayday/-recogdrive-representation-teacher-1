"""Retain one allocated DLC node; accept only task-scoped, hashed commands."""
from __future__ import annotations

import argparse
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Output outside task directory')
    data = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    for attempt in range(5):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
            temporary.write_text(data)
            temporary.replace(path)
            return
        except OSError as error:
            if error.errno not in {errno.ESTALE, errno.EIO, errno.ETIMEDOUT, errno.EAGAIN} or attempt == 4:
                raise
            time.sleep(min(0.25 * 2 ** attempt, 4))


def runtime_probe():
    mounts = {}
    for name in ['/mnt/workspace', '/mnt/data', '/mnt/yehr_workspace']:
        path = Path(name)
        mounts[name] = {'exists': path.is_dir(), 'resolved': str(path.resolve())}
        if path.is_dir():
            mounts[name]['filesystem_readonly'] = bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    return {'hostname': socket.gethostname(), 'python': sys.executable,
            'cpu_affinity': len(os.sched_getaffinity(0)), 'mounts': mounts,
            'model_loaded': False, 'experiment_started': False}


def main(args):
    folder = Path(args.node_dir).resolve()
    if not folder.is_relative_to(ROOT / 'resources'):
        raise ValueError('Unexpected node directory')
    if args.probe_only:
        print(json.dumps(runtime_probe(), ensure_ascii=False))
        return
    host = socket.gethostname()
    match = re.match(r'^(dlc[a-zA-Z0-9]+)(?:-|$)', host)
    if not match:
        raise ValueError('Resident must run inside its DLC container')
    job = match.group(1)
    output = folder / 'runtime' / job
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'resident.lock').open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        atomic(output / 'STARTUP.json', dict(time=stamp(), job=job, pid=os.getpid(), **runtime_probe()))
        processes = {}
        handles = []
        while True:
            try:
                binding_path = folder / 'SUBMITTED.json'
                binding = json.loads(binding_path.read_text()) if binding_path.exists() else {}
                authorized = binding.get('job') == job
                if authorized:
                    for command_path in sorted((folder / 'commands' / 'pending').glob('*.json')):
                        receipt = folder / 'commands' / 'receipts' / command_path.name
                        if receipt.exists():
                            continue
                        command = json.loads(command_path.read_text())
                        if command.get('expected_job') != job:
                            raise ValueError('Command job identity mismatch')
                        script = (ROOT / command['script']).resolve()
                        if not script.is_relative_to(ROOT / 'code') or not script.is_file():
                            raise ValueError('Command outside task code')
                        if hashlib.sha256(script.read_bytes()).hexdigest() != command['source_sha256']:
                            raise ValueError('Command source changed')
                        arguments = command['arguments']
                        if not isinstance(arguments, list) or not all(isinstance(x, str) for x in arguments):
                            raise ValueError('Invalid command arguments')
                        receipt.parent.mkdir(parents=True, exist_ok=True)
                        with receipt.open('x') as stream:
                            json.dump({'status': 'CLAIMED', 'time': stamp(), 'job': job}, stream)
                        log = folder / 'commands' / 'logs' / (command_path.stem + '.log')
                        log.parent.mkdir(parents=True, exist_ok=True)
                        handle = log.open('a')
                        handles.append(handle)
                        process = subprocess.Popen([sys.executable, '-u', '-B', str(script), *arguments],
                                                   cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                        processes[command_path.name] = process
                        atomic(receipt, {'status': 'LAUNCHED', 'time': stamp(), 'job': job,
                                         'pid': process.pid, 'source_sha256': command['source_sha256']})
                states = {}
                for name, process in processes.items():
                    code = process.poll()
                    value = {'status': 'RUNNING' if code is None else 'COMPLETE' if code == 0 else 'FAILED',
                             'time': stamp(), 'job': job, 'pid': process.pid, 'returncode': code}
                    states[name] = value
                    atomic(folder / 'commands' / 'states' / name, value)
                atomic(folder / 'LIVE.json', {'status': 'READY_IDLE' if authorized else 'WAITING_IDENTITY_BINDING',
                       'time': stamp(), 'job': job, 'hostname': host, 'pid': os.getpid(),
                       'identity_verified': authorized, 'children': states, 'main_retained': True,
                       'automatic_release': False, 'experiment_autostart': False})
            except Exception as error:
                atomic(output / 'LAST_ERROR.json', {'status': 'RESIDENT_ERROR_RETAINED', 'time': stamp(),
                       'job': job, 'error': repr(error), 'traceback': traceback.format_exc()})
            time.sleep(args.poll_seconds)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--node-dir', required=True)
    parser.add_argument('--poll-seconds', type=float, default=60)
    parser.add_argument('--probe-only', action='store_true')
    main(parser.parse_args())
