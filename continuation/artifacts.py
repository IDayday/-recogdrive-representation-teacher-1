"""Independent tar volumes, member hashes, bounded extraction and atomic receipts."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from continuation.layout import inside,sha,write_json

class HashedReader:
    def __init__(self,stream):self.stream=stream;self.hasher=hashlib.sha256()
    def read(self,size=-1):
        data=self.stream.read(size);self.hasher.update(data);return data

def pack_volume(destination,files,source_root,volume_id):
    destination=Path(destination);source_root=Path(source_root)
    destination.parent.mkdir(parents=True,exist_ok=True)
    receipt=destination.with_name(destination.name+'.json')
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if sha(destination)==old['sha256']:return old
        raise ValueError('Existing volume checksum mismatch')
    temporary=destination.with_name(destination.name+'.partial')
    manifest=dict(schema=1,id=volume_id,files=files)
    with tarfile.open(temporary,'w',format=tarfile.PAX_FORMAT) as archive:
        payload=(json.dumps(manifest,separators=(',',':'))+'\n').encode()
        meta=tarfile.TarInfo('VOLUME.json');meta.size=len(payload);meta.mtime=0;archive.addfile(meta,io.BytesIO(payload))
        for item in files:
            source=inside(source_root,item['source_path']);info=tarfile.TarInfo(item['path'])
            info.size=source.stat().st_size;info.mtime=0;info.mode=0o600
            if info.size!=item['bytes']:raise ValueError('Source size changed: '+str(source))
            with source.open('rb') as stream:
                reader=HashedReader(stream);archive.addfile(info,reader)
            if reader.hasher.hexdigest()!=item['sha256']:raise ValueError('Source changed or hash mismatch: '+str(source))
    if temporary.stat().st_size>=2*(1<<30):raise ValueError('Volume exceeds GitHub asset size limit')
    temporary.replace(destination)
    result=dict(schema=1,id=volume_id,name=destination.name,bytes=destination.stat().st_size,
                sha256=sha(destination),files=len(files))
    write_json(receipt,result);return result

def install_volume(path,workspace,expected_sha256):
    path=Path(path);workspace=Path(workspace).resolve()
    if sha(path)!=expected_sha256:raise ValueError('Downloaded volume checksum mismatch')
    with tarfile.open(path,'r:') as archive:
        first=archive.next()
        if first is None or first.name!='VOLUME.json' or not first.isfile():raise ValueError('Missing volume manifest')
        manifest=json.load(archive.extractfile(first));expected={x['path']:x for x in manifest['files']}
        if len(expected)!=len(manifest['files']):raise ValueError('Duplicate member paths')
        seen=set()
        for member in archive:
            if member.name=='VOLUME.json':continue
            if not member.isfile() or member.name not in expected or member.name in seen:raise ValueError('Unexpected archive member')
            item=expected[member.name];seen.add(member.name);dest=inside(workspace,member.name)
            if member.size!=item['bytes']:raise ValueError('Archive member size mismatch')
            if dest.exists():
                if sha(dest)!=item['sha256']:raise ValueError('Refusing to overwrite a different existing file: '+str(dest))
                continue
            dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_name(dest.name+'.'+str(os.getpid())+'.partial')
            hasher=hashlib.sha256()
            with archive.extractfile(member) as inp,temp.open('wb') as out:
                for block in iter(lambda:inp.read(8<<20),b''):out.write(block);hasher.update(block)
            if hasher.hexdigest()!=item['sha256']:
                temp.unlink();raise ValueError('Extracted file checksum mismatch')
            temp.replace(dest)
        if seen!=set(expected):raise ValueError('Incomplete archive')
    write_json(workspace/'.installed'/f"{manifest['id']}.json",dict(sha256=expected_sha256,files=len(seen)))
    return len(seen)
