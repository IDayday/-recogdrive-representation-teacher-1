"""Minimal ACS3 client; temporary credentials remain in memory only."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid


def request(service, version, action, method, path, query=None, payload=None):
    credential_uri = os.environ['ALIBABA_CLOUD_CREDENTIALS_URI']
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with direct.open(credential_uri, timeout=15) as response:
        credentials = json.load(response)
    if 'Credentials' in credentials:
        credentials = credentials['Credentials']
    region = os.environ['REGION']
    host = f'{service}.{region}.aliyuncs.com'
    body = b'' if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    content_hash = hashlib.sha256(body).hexdigest()
    headers = {
        'host': host, 'x-acs-action': action, 'x-acs-version': version,
        'x-acs-date': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'x-acs-signature-nonce': str(uuid.uuid4()), 'x-acs-content-sha256': content_hash,
        'x-acs-security-token': credentials['SecurityToken'],
    }
    if payload is not None:
        headers['content-type'] = 'application/json'
    signed = ';'.join(sorted(headers))
    canonical_headers = ''.join(f'{k}:{headers[k].strip()}\n' for k in sorted(headers))
    quote = lambda value: urllib.parse.quote(str(value), safe='-_.~')
    canonical_path = '/'.join(quote(piece) for piece in path.split('/'))
    qs = '&'.join(f'{quote(k)}={quote(v)}' for k, v in sorted((query or {}).items()))
    canonical = '\n'.join([method, canonical_path, qs, canonical_headers, signed, content_hash])
    string_to_sign = 'ACS3-HMAC-SHA256\n' + hashlib.sha256(canonical.encode()).hexdigest()
    signature = hmac.new(credentials['AccessKeySecret'].encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers['Authorization'] = f"ACS3-HMAC-SHA256 Credential={credentials['AccessKeyId']},SignedHeaders={signed},Signature={signature}"
    req = urllib.request.Request('https://' + host + canonical_path + ('?' + qs if qs else ''),
                                 data=body if payload is not None else None, headers=headers, method=method)
    try:
        with direct.open(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Never print Request headers, the credentials URI, or credentials.
        raw = error.read().decode(errors='replace')
        try:
            value = json.loads(raw)
            allowed = {k: value[k] for k in ['Code', 'Message', 'RequestId'] if k in value}
        except ValueError:
            allowed = {'status': error.code, 'reason': error.reason}
        raise RuntimeError(json.dumps(allowed, ensure_ascii=False)) from None


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['inspect', 'get', 'submit'])
    parser.add_argument('--job-id')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'inspect':
        dsw = request('pai-dsw', '2022-01-01', 'GetInstance', 'GET',
                      '/api/v2/instances/' + os.environ['DSW_INSTANCE_ID'])
        fields = ['InstanceId', 'InstanceName', 'Status', 'ImageId', 'ImageName', 'ImageUrl',
                  'EcsSpec', 'ResourceId', 'ResourceType', 'WorkspaceId', 'Datasets', 'UserVpc',
                  'Cpu', 'Gpu', 'Memory', 'AcceleratorType', 'InstanceType', 'ResourceGroupId']
        dsw = {k: dsw[k] for k in fields if k in dsw}
        jobs = request('pai-dlc', '2020-12-03', 'ListJobs', 'GET', '/api/v1/jobs',
                       {'WorkspaceId': os.environ['PAI_WORKSPACE_ID'], 'PageSize': 30})
        rows = jobs.get('Jobs', [])
        summary = [{k: row[k] for k in ['JobId', 'DisplayName', 'Status', 'ResourceId', 'JobType', 'GmtCreateTime'] if k in row} for row in rows]
        save(args.output, {'dsw': dsw, 'jobs': summary})
        print(json.dumps({'dsw': dsw, 'jobs': summary}, ensure_ascii=False))
    elif args.command == 'get':
        job = request('pai-dlc', '2020-12-03', 'GetJob', 'GET', '/api/v1/jobs/' + args.job_id)
        fields = ['JobId', 'DisplayName', 'Status', 'ReasonCode', 'ReasonMessage', 'ResourceId', 'WorkspaceId',
                  'JobType', 'JobSpecs', 'UserVpc', 'DataSources', 'UserCommand', 'GmtCreateTime', 'GmtStartTime', 'GmtEndTime', 'Settings']
        result = {k: job[k] for k in fields if k in job}
        for spec in result.get('JobSpecs', []):
            spec.pop('ImageConfig', None)
        save(args.output, result)
        print(json.dumps(result, ensure_ascii=False))
    else:
        body = json.loads(args.request.read_text())
        result = request('pai-dlc', '2020-12-03', 'CreateJob', 'POST', '/api/v1/jobs', payload=body)
        result = {k: result[k] for k in ['JobId', 'RequestId'] if k in result}
        save(args.output, result)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
