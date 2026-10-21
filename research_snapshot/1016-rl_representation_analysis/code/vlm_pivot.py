"""Overlap collection with a single-pass transpose on each high-memory node.

Buffers are rebuildable from durable collection chunks. Only complete cell files
receive atomic receipts; unfinished buffers are never represented as accepted data.
"""
from common import *
import argparse
import io
import uuid
import numpy as np
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT,VISION_GROUPS,LANGUAGE_GROUPS

def plan():
    first=read(VOUT/'ENGINEERING_SMOKE_v2.json')['checks'][0]['block_shapes'];totals=[0,0];blocks=[]
    for name,shape in sorted(first.items(),key=lambda item:-np.prod(item[1])):
        owner=int(np.argmin(totals));size=int(np.prod(shape));totals[owner]+=size
        blocks.append(dict(name=name,shape=shape,owner=owner,groups=VISION_GROUPS if name.startswith(('vision','bridge')) else LANGUAGE_GROUPS))
    path=VOUT/'PIVOT_PLAN.json';assert not path.exists()
    atomic(path,dict(status='FROZEN',time=stamp(),blocks=blocks,float32_values_per_scene=totals,
        expected_cases=103288,expected_cells=sum(len(b['groups']) for b in blocks),all_module_and_group_shapes_from_real_smoke=True))
    print(json.dumps(dict(status='PREPARED',cells=sum(len(b['groups']) for b in blocks),buffer_GiB=[v*103288*4/1024**3 for v in totals])),flush=True)

def save_array(path,array):
    assert not path.exists();path.parent.mkdir(parents=True,exist_ok=True)
    stream=io.BytesIO();np.save(stream,array,allow_pickle=False);view=stream.getbuffer()
    hashed=hashlib.sha256(view).hexdigest();tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('wb') as output:output.write(view)
    tmp.replace(path);return hashed

def run(node,limit=None):
    setup(f'vlm_repair/pivot/node{node}');import psutil
    base=ROOT/'runs/vlm_all_layers_20261016_v1';plan=read(VOUT/'PIVOT_PLAN.json');blocks=[b for b in plan['blocks'] if b['owner']==node];n=limit or plan['expected_cases']
    target=VOUT if limit is None else VOUT/'pivot_smoke'
    mapping=None if limit is None else {r['global_index']:i for i,r in enumerate(read(base/'panel.json')[:limit])}
    needed=sum(int(np.prod(b['shape'])) for b in blocks)*n*4
    assert psutil.virtual_memory().available>needed*1.1+(64 if limit is None else 2)*1024**3
    arrays={b['name']:np.empty((n,*b['shape']),dtype=np.float32) for b in blocks};seen=np.zeros(n,dtype=bool);processed=set();sources=[]
    status=target/f'pivot/node{node}_status.json';began=time.monotonic()
    while not seen.all():
        failures=list((base/'failures').glob('*.json'))+list(base.glob('node*/FAILED.json'))
        if failures:raise RuntimeError('Collection failure: '+str(failures[0]))
        paths=[p for p in sorted((base/'receipts').glob('collect_*.json')) if p.name not in processed and (limit is None or int(p.stem.split('_')[1])<limit)]
        if not paths:time.sleep(5);continue
        for path in paths:
            receipt=read(path);result_path=base/'results'/path.name;assert sha(result_path)==receipt['result_sha256'];result=read(result_path);source=ROOT/result['array_path']
            # Every source file is fully hash-checked by one node; ZIP members are CRC-checked on both readers.
            checked=int(result['task']['start']//16)%2==node
            if checked:assert sha(source)==result['array_sha256']
            with np.load(source,allow_pickle=False) as data:
                indices=np.asarray(data['global_indices'])
                assert indices.tolist()==[r['global_index'] for r in result['records']]
                if mapping is not None:indices=np.array([mapping[int(i)] for i in indices])
                assert not seen[indices].any()
                for b in blocks:
                    value=np.asarray(data[b['name']]);assert value.dtype==np.float32 and list(value.shape[1:])==b['shape']
                    valid=np.isfinite(value).all(-1);missing=np.isnan(value).all(-1);assert (valid|missing).all()
                    arrays[b['name']][indices]=value
            seen[indices]=True;processed.add(path.name);sources.append(dict(path=result['array_path'],sha256=result['array_sha256'],whole_file_hash_verified_here=checked))
        atomic(status,dict(status='READING',time=stamp(),node=node,chunks=len(processed),scenes=int(seen.sum()),total=n,seconds=time.monotonic()-began))
    assert len(processed)==(read(base/'PROTOCOL.json')['tasks'] if limit is None else (limit+15)//16)
    cells=[]
    for b in blocks:
        values=arrays[b['name']]
        for j,group in enumerate(b['groups']):
            name=b['name']+'__'+group;path=target/'cells'/(name+'.npy');value=values[:,j,:]
            valid=np.isfinite(value).all(-1);assert (valid|np.isnan(value).all(-1)).all()
            h=save_array(path,value);record=dict(status='COMPLETE',time=stamp(),cell=name,block=b['name'],group=group,group_index=j,owner=node,
                path=str(path.relative_to(ROOT)),sha256=h,shape=list(value.shape),valid_cases=int(valid.sum()),missing_cases=int((~valid).sum()))
            atomic(path.with_suffix('.json'),record);cells.append(record)
        del arrays[b['name']]
        atomic(status,dict(status='WRITING_CELLS',time=stamp(),node=node,cells=len(cells),blocks_left=len(arrays),seconds=time.monotonic()-began))
    atomic(target/f'CACHE_NODE{node}.json',dict(status='PASS',time=stamp(),node=node,cells=cells,sources=sources,all_cases_seen_once=True,
        source_hash_assignment='chunk index modulo 2',seconds=time.monotonic()-began))
    atomic(status,dict(status='COMPLETE',time=stamp(),node=node,cells=len(cells)));print(json.dumps(dict(status='PASS',node=node,cells=len(cells))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--node',type=int);p.add_argument('--limit',type=int);a=p.parse_args()
    setup('vlm_repair/pivot_setup');plan() if a.mode=='prepare' else run(a.node,a.limit)
