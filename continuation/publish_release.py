"""Create/resume a draft Release; publish only after every asset is verified.

SSH keys authenticate git transport. Release upload uses a repository-scoped
GitHub token from GITHUB_TOKEN/GH_TOKEN or an explicitly supplied private file.
Credentials are never printed, included in URLs, or stored in receipts.
"""
from __future__ import annotations
import argparse
import http.client
import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request
from continuation.layout import sha,write_json

class APIError(RuntimeError):pass

def api(path,token,method='GET',payload=None):
    body=None if payload is None else json.dumps(payload).encode()
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','User-Agent':'recogdrive-continuation'}
    if body is not None:headers['Content-Type']='application/json'
    request=urllib.request.Request('https://api.github.com'+path,data=body,headers=headers,method=method)
    try:
        with urllib.request.urlopen(request,timeout=60)as response:return json.load(response)
    except urllib.error.HTTPError as error:raise APIError(f'GitHub API HTTP {error.code} for {method} {path}')from None

def upload(url,path,token):
    path=Path(path);parts=urllib.parse.urlsplit(url.split('{',1)[0])
    if parts.scheme!='https' or parts.hostname!='uploads.github.com':raise ValueError('Unexpected GitHub upload host')
    connection=http.client.HTTPSConnection(parts.hostname,timeout=120,context=ssl.create_default_context())
    target=parts.path+'?'+urllib.parse.urlencode({'name':path.name})
    connection.putrequest('POST',target)
    for key,value in {'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size),
        'User-Agent':'recogdrive-continuation','X-GitHub-Api-Version':'2022-11-28'}.items():connection.putheader(key,value)
    connection.endheaders();sent=0;next_progress=128<<20
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(4<<20),b''):
            connection.send(block);sent+=len(block)
            if sent>=next_progress:
                print(json.dumps(dict(uploading=path.name,sent_bytes=sent,total_bytes=path.stat().st_size)),flush=True)
                next_progress+=128<<20
    response=connection.getresponse();body=response.read(1<<20);status=response.status;connection.close()
    if status!=201:raise APIError(f'GitHub asset upload HTTP {status}: {path.name}')
    return json.loads(body)

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--token-file')
    p.add_argument('--commit',required=True);p.add_argument('--notes',required=True);a=p.parse_args()
    token=Path(a.token_file).read_text().strip()if a.token_file else os.environ.get('GITHUB_TOKEN')or os.environ.get('GH_TOKEN')
    if not token:raise APIError('Release upload needs repository Contents:write API authentication; SSH git authentication is separate')
    directory=Path(a.directory);manifest_path=directory/'RELEASE_MANIFEST.json';manifest=json.loads(manifest_path.read_text())
    repo=manifest['repository'];tag=manifest['tag'];prefix='/repos/'+repo
    # Check every local volume before creating or changing an external release.
    for item in manifest['assets']:
        path=directory/item['name']
        if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:raise ValueError('Local release volume failed verification')
    try:release=api(prefix+'/releases/tags/'+urllib.parse.quote(tag,safe=''),token)
    except APIError as error:
        if 'HTTP 404 'not in str(error):raise
        release=api(prefix+'/releases',token,'POST',dict(tag_name=tag,target_commitish=a.commit,
            name='ReCogDrive representation repair and H/T/HT continuation',body=Path(a.notes).read_text(),draft=True))
    if not release['draft']:raise APIError('Existing published release is immutable to this tool; choose a new tag')
    assets=[]
    for page in range(1,100):
        rows=api(prefix+f"/releases/{release['id']}/assets?per_page=100&page={page}",token);assets.extend(rows)
        if len(rows)<100:break
    existing={x['name']:x for x in assets};files=manifest['assets']+[dict(name=manifest_path.name,bytes=manifest_path.stat().st_size,sha256=sha(manifest_path))]
    receipts=[]
    for item in files:
        remote=existing.get(item['name'])
        if remote is None:remote=upload(release['upload_url'],directory/item['name'],token)
        if remote['size']!=item['bytes'] or remote.get('digest')!='sha256:'+item['sha256']:
            raise APIError('Remote asset digest mismatch: '+item['name'])
        receipts.append({k:remote.get(k)for k in ['id','name','size','digest','browser_download_url']})
        write_json(directory/'UPLOAD_PROGRESS.json',dict(release_id=release['id'],verified=receipts,total=len(files)))
        print(json.dumps(dict(verified=item['name'],completed=len(receipts),total=len(files))),flush=True)
    release=api(prefix+f"/releases/{release['id']}",token,'PATCH',dict(draft=False))
    write_json(directory/'PUBLISHED.json',dict(url=release['html_url'],tag=tag,commit=a.commit,verified_assets=receipts))
    print(release['html_url'])

if __name__=='__main__':main()
