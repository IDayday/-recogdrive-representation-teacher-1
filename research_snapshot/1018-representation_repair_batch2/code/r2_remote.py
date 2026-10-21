"""Verified DLC web-terminal commands; session URLs and credentials never persisted."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from dlc_cloud import request
from r2_common import ROOT, atomic, read, stamp


def execute(job, command, timeout=50):
    import websocket
    profile = {'region': 'cn-wulanchabu', 'workspace_id': '245760', 'auth': {'kind': 'instance_role'}}
    d = request(profile, 'pai-dlc', '2020-12-03', 'GetJob', 'GET', '/api/v1/jobs/' + job)
    assert d['JobId'] == job and d['Status'] == 'Running'
    assert str(d['WorkspaceId']) == profile['workspace_id']
    pod = next(x for x in d['Pods'] if x['Status'] == 'Running')
    response = request(profile, 'pai-dlc', '2020-12-03', 'GetWebTerminal', 'GET',
                       f'/api/v1/jobs/{job}/pods/{pod["PodId"]}/webterminal', query={'IsShared': 'true'})
    marker = 'R2_EXIT_' + uuid.uuid4().hex
    began = time.monotonic(); output = ''; connection = None
    try:
        connection = websocket.create_connection(response['WebTerminalUrl'], timeout=15, http_no_proxy=['*'])
        connection.send(json.dumps({'operation': 'stdin', 'data': command + f'\nprintf "\\n{marker}:%s\\n" "$?"\n'}))
        while time.monotonic() - began < timeout:
            connection.settimeout(min(10, max(1, timeout - (time.monotonic() - began))))
            try: value = json.loads(connection.recv())
            except websocket.WebSocketTimeoutException: continue
            if value.get('operation') == 'stdout': output += value.get('data', '')
            found = re.search(r'(?:\r?\n)' + marker + r':(\d+)(?:\r?\n)', output)
            if found:
                code = int(found.group(1))
                return {'status': 'PASS' if code == 0 else 'COMMAND_FAILED', 'time': stamp(),
                        'job': job, 'pod': pod['PodId'], 'exit_code': code, 'output': output,
                        'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
                        'terminal_url_saved': False, 'seconds': time.monotonic() - began}
        raise TimeoutError('DLC terminal command timeout')
    finally:
        if connection is not None: connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--command-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = Path(args.command_file).resolve()
    assert source.is_relative_to(ROOT)
    result = execute(args.job, source.read_text())
    atomic(ROOT / args.output, result)
    print(json.dumps({k: result[k] for k in ['status', 'job', 'exit_code', 'seconds']}))
    assert result['exit_code'] == 0
