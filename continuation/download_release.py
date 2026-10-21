"""Resume public Release downloads, verify SHA256, then install selected profiles."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request
from continuation.artifacts import install_volume
from continuation.layout import REPO,sha

def download(url,destination,size=None,expected=None):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        if expected and sha(destination)!=expected:raise ValueError('Existing download checksum mismatch')
        return destination
    partial=destination.with_name(destination.name+'.partial');offset=partial.stat().st_size if partial.exists()else 0
    headers={'User-Agent':'recogdrive-continuation'}
    if offset:headers['Range']=f'bytes={offset}-'
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=90) as response:
        append=bool(offset and response.status==206)
        if append and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
            raise ValueError('Server returned an unexpected download range')
        with partial.open('ab' if append else 'wb') as out:
            for block in iter(lambda:response.read(8<<20),b''):out.write(block)
    if size is not None and partial.stat().st_size!=size:raise ValueError('Incomplete download; rerun to resume')
    if expected and sha(partial)!=expected:raise ValueError('Downloaded checksum mismatch')
    partial.replace(destination);return destination

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--cache',required=True)
    p.add_argument('--tag',default='continuation-20261022');p.add_argument('--repository',default='IDayday/-recogdrive-representation-teacher-1')
    p.add_argument('--profiles',default='resume,teacher_train,metrics_development');p.add_argument('--from-dir')
    p.add_argument('--keep-volumes',action='store_true');a=p.parse_args()
    workspace=Path(a.workspace).resolve();cache=Path(a.cache).resolve()
    if not (workspace/'PORTABLE_WORKSPACE.json').exists():raise ValueError('Run continuation.prepare first')
    base=f'https://github.com/{a.repository}/releases/download/{a.tag}/'
    manifest=Path(a.from_dir)/'RELEASE_MANIFEST.json' if a.from_dir else download(base+'RELEASE_MANIFEST.json',cache/'RELEASE_MANIFEST.json')
    pinned=REPO/'continuation/RELEASE.json'
    if pinned.exists():
        identity=json.loads(pinned.read_text())
        if identity['tag']==a.tag and sha(manifest)!=identity['manifest_sha256']:raise ValueError('Release manifest differs from the code-pinned snapshot')
    data=json.loads(manifest.read_text());profiles=set(a.profiles.split(','))
    if not profiles<=set(data['profiles']):raise ValueError('Unknown profile')
    for item in data['assets']:
        if item['profile'] not in profiles:continue
        receipt=workspace/'.installed'/(item['id']+'.json')
        if receipt.exists() and json.loads(receipt.read_text())['sha256']==item['sha256']:continue
        source=Path(a.from_dir)/item['name'] if a.from_dir else download(base+item['name'],cache/item['name'],item['bytes'],item['sha256'])
        count=install_volume(source,workspace,item['sha256'])
        print(json.dumps(dict(installed=item['name'],files=count,profile=item['profile'])),flush=True)
        if not a.from_dir and not a.keep_volumes:source.unlink()

if __name__=='__main__':main()
