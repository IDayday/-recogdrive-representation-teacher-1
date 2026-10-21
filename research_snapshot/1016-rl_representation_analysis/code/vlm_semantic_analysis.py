"""Independent immutable transpose and CPU scan preparation for the two corrected spans."""
from common import *
import numpy as np
import io,uuid,shutil
from vlm_semantic import SEM,GROUPS
from vlm_semantic_collect import BASE
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT

def cache():
    import psutil
    plan=read(BASE/'PROTOCOL.json');paths=sorted((BASE/'receipts').glob('*.json'));assert len(paths)==plan['tasks']==6456
    first=read(BASE/'results'/paths[0].name)
    with np.load(ROOT/first['array_path']) as a:shapes={k:list(a[k].shape[1:]) for k in a.files if k!='global_indices'}
    need=103288*sum(np.prod(v) for v in shapes.values())*4;assert psutil.virtual_memory().available>need*1.3+8*1024**3
    arrays={k:np.empty((103288,*v),dtype='float32') for k,v in shapes.items()};seen=np.zeros(103288,dtype=bool);sources=[]
    for p in paths:
        proof=read(p);rpath=BASE/'results'/p.name;assert sha(rpath)==proof['result_sha256'];r=read(rpath);source=ROOT/r['array_path'];assert sha(source)==r['array_sha256']
        with np.load(source) as a:
            idx=a['global_indices'];assert not seen[idx].any();seen[idx]=True
            for k in shapes:
                value=np.asarray(a[k]);assert value.dtype==np.float32 and np.isfinite(value).all();arrays[k][idx]=value
        sources.append(dict(path=r['array_path'],sha256=r['array_sha256']))
    assert seen.all();cells=[];blocks=[]
    for i,(name,values) in enumerate(arrays.items()):
        blocks.append(dict(name=name,shape=shapes[name],owner=i%2,groups=GROUPS))
        for j,group in enumerate(GROUPS):
            cell=name+'__'+group;path=SEM/'cells'/(cell+'.npy');path.parent.mkdir(exist_ok=True);stream=io.BytesIO();np.save(stream,values[:,j,:]);payload=stream.getbuffer();hashed=hashlib.sha256(payload).hexdigest()
            if path.exists():assert sha(path)==hashed
            else:
                temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
                with temporary.open('wb') as f:f.write(payload)
                temporary.replace(path)
            constant=bool(np.array_equal(values[:,j,:],np.broadcast_to(values[0,j,:],values[:,j,:].shape)))
            record=dict(status='COMPLETE',time=stamp(),constant_across_cases=constant,cell=cell,block=name,group=group,owner=i%2,group_index=j,path=str(path.relative_to(ROOT)),sha256=hashed,shape=[103288,values.shape[-1]],valid_cases=103288,missing_cases=0,corrected_bpe_span=True)
            atomic(path.with_suffix('.json'),record);cells.append(record)
    atomic(SEM/'PIVOT_PLAN.json',dict(status='FROZEN',time=stamp(),blocks=blocks,expected_cases=103288,expected_cells=64))
    atomic(SEM/'CACHE_COMPLETE.json',dict(status='PASS',time=stamp(),cases=103288,cells=cells,sources=sources,all_source_hashes_verified=True,all_regions_present=True))

def prepare():
    plan=read(SEM/'PIVOT_PLAN.json');tasks=[dict(id=b['name']+'__'+g,cell=b['name']+'__'+g,owner=b['owner'],block=b['name']) for b in plan['blocks'] for g in GROUPS]
    for kind in ['rapid','scan']:
        folder=SEM/kind
        if not (folder/'tasks.json').exists():atomic(folder/'tasks.json',tasks)
        assert read(folder/'tasks.json')==tasks
        for name in ['CONFIGS.json','numeric_reference.npz','NUMERIC_REFERENCE.json']:
            target=folder/name;src=VOUT/kind/name
            if target.exists():assert sha(target)==sha(src)
            else:shutil.copyfile(src,target)
    atomic(SEM/'ANALYSIS_EXECUTION.json',dict(status='FROZEN',time=stamp(),code_sha256={'code/'+p:sha(ROOT/'code'/p) for p in ['vlm_semantic_analysis.py','vlm_semantic_cpu.py','vlm_scan.py','vlm_scan_queue.py','vlm_space.py','vlm_rapid.py','vlm_rapid_queue.py','vlm_rapid_space.py']},cells=64,session_folds=5,all_train_cases=103288,full_grid_configs=11633,rapid_configs=81))

def main():
    setup('vlm_semantic_v2/analysis_controller')
    while len(list((BASE/'receipts').glob('*.json')))!=6456:time.sleep(30)
    if not (SEM/'CACHE_COMPLETE.json').exists():cache()
    prepare();print('CORRECTED_SEMANTIC_ANALYSIS_READY',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(VOUT/'failures/semantic_analysis_controller.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
