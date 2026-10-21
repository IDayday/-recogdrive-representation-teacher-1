"""Lossless cell caches from existing representation arrays. Never imports a planner.
Large buffers are allowed only inside the retained 1.7TB nodes, after repair report acceptance.
"""
from common import *
import io
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT=ROOT/'analysis/subspace_scan_v2'
TIMES=[80,60,40,20,0]

def name(route,start,step,layer,token):return f'{route}_a{start}_s{step}_l{layer:02d}_t{token}'

def save(path,x):
    import uuid
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists()
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('wb') as f:np.save(f,x,allow_pickle=False)
    tmp.replace(path);return sha(path)

def natural(node):
    steps=[i for i in range(5) if i%2==node];meta=read(ROOT/'manifests/natural_s0.json');n=len(meta)
    x=np.empty((len(steps),18,8,n,384),dtype=np.float32);z=np.empty((len(steps),8,n,512),dtype=np.float32);seen=np.zeros(n,dtype=bool)
    paths=sorted((ROOT/'runs/natural_s0_repr_20261016T080905Z/formal').glob('rank*/chunks/*.json'));assert len(paths)==3232
    def load(p):
        doc=read(p);data=retry(lambda:Path(doc['array_path']).read_bytes());assert hashlib.sha256(data).hexdigest()==doc['array_sha256']
        with np.load(io.BytesIO(data),allow_pickle=False) as a:
            h=np.array(a['representations'][:,steps]);out=np.array(a['dit_output'][:,steps])
        return doc,h,out
    sources=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,(doc,h,out) in enumerate(pool.map(load,paths),1):
            idx=np.array([r['global_index'] for r in doc['records']]);assert not seen[idx].any();seen[idx]=True
            for j in range(len(steps)):x[j,:,:,idx,:]=np.moveaxis(h[:,j],0,0);z[j,:,idx,:]=np.moveaxis(out[:,j],0,0)
            sources.append(dict(path=doc['array_path'],sha256=doc['array_sha256']))
            if i%128==0:print(json.dumps(dict(status='NATURAL_CACHE_READ',node=node,chunks=i,total=len(paths))),flush=True)
    assert seen.all();files=[]
    for j,s in enumerate(steps):
        for layer in range(19):
            for token in range(8):
                cell=name('r1',-1,s,layer,token);a=x[j,layer,token] if layer<18 else z[j,token]
                path=OUT/'cache'/(cell+'.npy');h=save(path,a);files.append(dict(cell=cell,path=str(path),sha256=h,shape=list(a.shape)))
    atomic(OUT/f'cache/NATURAL_NODE{node}.json',dict(status='PASS',time=stamp(),files=files,sources=sources,all_source_hashes_verified=True,n=n))

def paired(node):
    from paired_acceptance import load_records
    records=load_records('paired_formal_20261016T0728Z','formal');assert len(records)==45760
    meta=read(ROOT/'analysis/observation_v1/cache/metadata.json');n=len(meta);by={r['token']:i for i,r in enumerate(meta)}
    files=[];sources=[]
    for start in TIMES:
        if TIMES.index(start)%2!=node:continue
        steps=TIMES[TIMES.index(start):];q=np.full((2,n,2),np.nan);seen=np.zeros((2,n,2),dtype=bool)
        x=np.empty((len(steps),18,8,2,n,2,384),dtype=np.float32);z=np.empty((len(steps),8,2,n,2,512),dtype=np.float32)
        rows=[r for r in records if r['start_t']==start]
        paths={r['array_path']:r for r in rows};assert len(paths)==2*n
        def load(r):
            raw=retry(lambda:Path(r['array_path']).read_bytes());assert hashlib.sha256(raw).hexdigest()==r['array_sha256']
            with np.load(io.BytesIO(raw),allow_pickle=False) as a:
                assert a['timesteps'].tolist()==steps
                return r,np.array(a['representations']),np.array(a['dit_output'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            for r,h,out in pool.map(load,paths.values()):
                g=r['noise_group'];i=by[r['token']]
                x[:,:,:,g,i]=np.moveaxis(h,0,-2);z[:,:,g,i]=np.moveaxis(out,0,-2)
                sources.append(dict(path=r['array_path'],sha256=r['array_sha256']))
        for r in rows:
            g=r['noise_group'];i=by[r['token']];b=r['branch_index'];assert not seen[g,i,b];seen[g,i,b]=True;q[g,i,b]=r['score']['score']
        assert seen.all() and np.isfinite(q).all();save(OUT/f'cache/r2_a{start}_scores.npy',q)
        for j,t in enumerate(steps):
            s=TIMES.index(t)
            for layer in range(19):
                for token in range(8):
                    cell=name('r2',start,s,layer,token);a=x[j,layer,token] if layer<18 else z[j,token]
                    path=OUT/'cache'/(cell+'.npy');h=save(path,a);files.append(dict(cell=cell,path=str(path),sha256=h,shape=list(a.shape)))
        print(json.dumps(dict(status='PAIRED_CACHE_START_DONE',node=node,start=start,cells=len(files))),flush=True)
    atomic(OUT/f'cache/PAIRED_NODE{node}.json',dict(status='PASS',time=stamp(),files=files,sources=sources,all_source_hashes_verified=True,n=n))

def prepare(node):
    import psutil
    assert psutil.virtual_memory().available>400*1024**3,'Large cache preparation only on retained high-memory nodes'
    assert (ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json').exists(),'User requested repair report before expanded computation'
    OUT.mkdir(parents=True,exist_ok=True);natural(node);paired(node)
    atomic(OUT/f'cache/PREP_NODE{node}_COMPLETE.json',dict(status='PASS',time=stamp(),node=node))

def ensure_cache_index():
    """Mechanical preparation handoff runs inside DLC, independently of DSW monitor."""
    if (OUT/'CACHE_INDEX.json').exists():return True
    if not all((OUT/f'cache/PREP_NODE{i}_COMPLETE.json').exists() for i in [0,1]):return False
    claim=OUT/'cache/INDEX_CLAIM'
    try:claim.mkdir()
    except FileExistsError:return (OUT/'CACHE_INDEX.json').exists()
    atomic(claim/'OWNER.json',dict(pid=os.getpid(),hostname=os.uname().nodename,time=stamp()))
    cells={};proofs={}
    for node in [0,1]:
        for prefix in ['NATURAL','PAIRED']:
            path=OUT/f'cache/{prefix}_NODE{node}.json';doc=read(path);assert doc['status']=='PASS'
            proofs[str(path.relative_to(ROOT))]=sha(path)
            for row in doc['files']:assert row['cell'] not in cells;cells[row['cell']]=row
    assert len(cells)==3040,len(cells)
    atomic(OUT/'CACHE_INDEX.json',dict(status='PASS',time=stamp(),cells=cells,proofs_sha256=proofs,collection_rerun=False,index_created_inside_dlc=True))
    return True
