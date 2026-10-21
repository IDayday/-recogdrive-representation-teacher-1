"""Submit two own-account holding nodes. No stop/release operation is provided."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

from dlc_cloud import request
from dlc_resident import atomic, stamp

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / '1016-rl_representation_analysis'
API = ('pai-dlc', '2020-12-03')
SOURCE_JOB = 'dlc1mxzax7hcl8tx'
TEMPLATE = OLD / 'vlm_repair_v1/elastic_v1/nodes/elastic_006/REQUEST.json'
MINUTES = 4320  # Explicit user-approved exception to the 120h default.


def read(path):
    return json.loads(Path(path).read_text())


def profile():
    return {'region': os.environ['REGION'], 'workspace_id': os.environ['PAI_WORKSPACE_ID'],
            'quota_id': 'quotachw9oq5rg02', 'auth': {'kind': 'instance_role'}}


def call(action, method, path, **kwargs):
    return request(profile(), *API, action, method, path, **kwargs)


def prepare():
    p = profile()
    source = call('GetJob', 'GET', '/api/v1/jobs/' + SOURCE_JOB)
    template = read(TEMPLATE)
    assert source['ResourceId'] == template['ResourceId'] == p['quota_id']
    assert str(source['WorkspaceId']) == template['WorkspaceId'] == p['workspace_id']
    assert source['JobSpecs'][0]['Image'] == template['JobSpecs'][0]['Image']
    assert source['JobSpecs'][0]['ResourceConfig'] == template['JobSpecs'][0]['ResourceConfig']
    actual_mounts = {x['MountPath']: (x['Uri'], x['MountAccess']) for x in source['DataSources']}
    expected_mounts = {x['MountPath']: (x['Uri'], x['MountAccess']) for x in template['DataSources']}
    assert actual_mounts == expected_mounts
    assert expected_mounts['/mnt/data'][1] == expected_mounts['/mnt/yehr_workspace'][1] == 'RO'
    assert expected_mounts['/mnt/workspace'][1] == 'RW'
    quotas = request(p, 'pai', '2022-01-12', 'ListQuotas', 'GET', '/api/v1/quotas/',
                     query={'WorkspaceIds': p['workspace_id'], 'QuotaIds': p['quota_id'],
                            'ResourceType': 'Lingjun', 'Verbose': 'true', 'PageSize': 100})
    quota = next(x for x in quotas['Quotas'] if x['QuotaId'] == p['quota_id'])
    assert quota['Status'] == 'Ready'
    assert any(str(x['WorkspaceId']) == p['workspace_id'] for x in quota['Workspaces'])
    for key in ['VpcId', 'SwitchId', 'SecurityGroupId']:
        assert template['UserVpc'][key] == source['UserVpc'][key] == quota['QuotaConfig']['UserVpc'][key]
    for path in expected_mounts:
        assert Path(path).is_dir()
    identity = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = ROOT / 'resources' / ('self_' + identity)
    folder.mkdir(parents=True, exist_ok=False)
    source_files = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((ROOT / 'code').glob('dlc_*.py'))}
    details = quota['QuotaDetails']
    preflight = {'status': 'PASS_FOR_RESERVATION_ONLY', 'time': stamp(), 'source_job': SOURCE_JOB,
                 'source_template': str(TEMPLATE), 'source_template_sha256': hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
                 'profile': p, 'expected_user_id': source['UserId'], 'source_files': source_files,
                 'quota_name': quota.get('QuotaName'), 'pool_allocated': details['AllocatedQuota'],
                 'pool_total': details['ActualMinQuota'], 'empty_nodes': details['NodeStatistics'].get('EmptyNodeNum'),
                 'model_smoke_not_run': 'Resource reservation only; no experiment or model starts automatically.',
                 'existing_peer_jobs_user_reported': {
                     'dlcb46akrk2hji1u': 'Running', 'dlcgxxrm3yape59d': 'Running',
                     'dlcqdtslnqnytsc7': 'Running', 'dlcwhkv0rt5t8crx': 'Queuing'},
                 'existing_jobs_untouched': True, 'requested_runtime_minutes': MINUTES,
                 'user_approved_workspace_limit_exception': True,
                 'exception_evidence': 'Prior 7200min CreateJob was explicitly rejected; user approved 4320min for these two nodes.'}
    atomic(folder / 'PREFLIGHT.json', preflight)
    for index in range(2):
        node = folder / f'node{index}'
        body = copy.deepcopy(template)
        body.update(DisplayName=f'sjc-repair2-self-node{index}-{identity.lower()}',
                    JobMaxRunningTimeMinutes=MINUTES,
                    UserCommand=f'python3 -u -B {ROOT}/code/dlc_resident.py --node-dir {node}')
        assert len(body['JobSpecs']) == 1 and body['JobSpecs'][0]['PodCount'] == 1
        assert int(body['JobSpecs'][0]['ResourceConfig']['GPU']) == 16
        body['Settings'] = {'JobReservedMinutes': 0}
        atomic(node / 'REQUEST.json', body)
    atomic(ROOT / 'resources/LATEST.json', {'folder': str(folder.relative_to(ROOT)), 'time': stamp()})
    print('PREPARED', str(folder), flush=True)
    return folder


def status(folder, index):
    node = folder / f'node{index}'
    submission = read(node / 'SUBMITTED.json')
    body = read(node / 'REQUEST.json')
    d = call('GetJob', 'GET', '/api/v1/jobs/' + submission['job'])
    preflight = read(folder / 'PREFLIGHT.json')
    assert d['UserId'] == preflight['expected_user_id']
    for key in ['DisplayName', 'UserCommand', 'ResourceId', 'WorkspaceId']:
        assert str(d[key]) == str(body[key]), key
    assert d['JobMaxRunningTimeMinutes'] >= MINUTES
    assert int(d['JobSpecs'][0]['PodCount']) == 1
    assert int(d['JobSpecs'][0]['ResourceConfig']['GPU']) == 16
    assert {x['MountPath']: (x['Uri'], x['MountAccess']) for x in d['DataSources']} == {
        x['MountPath']: (x['Uri'], x['MountAccess']) for x in body['DataSources']}
    value = {'status': d['Status'], 'time': stamp(), 'job': d['JobId'], 'user_id': d['UserId'],
             'name': d['DisplayName'], 'max_running_minutes': d['JobMaxRunningTimeMinutes'],
             'reserved_minutes': d['Settings']['JobReservedMinutes'],
             'cards': 16, 'nodes': 1, 'region': profile()['region'], 'workspace': d['WorkspaceId'],
             'quota': d['ResourceId'], 'created': d.get('GmtCreateTime'),
             'running_since': d.get('GmtRunningTime'), 'reason': d.get('ReasonCode'),
             'reason_message': d.get('ReasonMessage'),
             'pods': [{'id': x['PodId'], 'status': x['Status']} for x in d.get('Pods', [])],
             'account_mounts_and_runtime_verified': True, 'user_approved_72h_exception': True}
    atomic(node / 'CLOUD_STATUS.json', value)
    print(json.dumps(value, ensure_ascii=False), flush=True)
    return value


def submit(folder):
    expected = read(folder / 'PREFLIGHT.json')['source_files']
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    for index in range(2):
        node = folder / f'node{index}'
        body = read(node / 'REQUEST.json')
        if not (node / 'SUBMITTED.json').exists():
            listed = call('ListJobs', 'GET', '/api/v1/jobs',
                          query={'WorkspaceId': profile()['workspace_id'], 'DisplayName': body['DisplayName'], 'PageSize': 100})
            existing = [x for x in listed.get('Jobs', []) if x.get('DisplayName') == body['DisplayName']]
            assert len(existing) <= 1
            response = {'JobId': existing[0]['JobId']} if existing else call('CreateJob', 'POST', '/api/v1/jobs', payload=body)
            atomic(node / 'SUBMITTED.json', {'status': 'SUBMITTED', 'time': stamp(), 'job': response['JobId'],
                   'request_id': response.get('RequestId'),
                   'request_sha256': hashlib.sha256((node / 'REQUEST.json').read_bytes()).hexdigest()})
            print('SUBMITTED', index, response['JobId'], flush=True)
        status(folder, index)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'submit', 'status'])
    parser.add_argument('--folder')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
    else:
        selected = Path(args.folder).resolve() if args.folder else ROOT / read(ROOT / 'resources/LATEST.json')['folder']
        assert selected.is_relative_to(ROOT / 'resources')
        submit(selected) if args.mode == 'submit' else [status(selected, i) for i in range(2)]
