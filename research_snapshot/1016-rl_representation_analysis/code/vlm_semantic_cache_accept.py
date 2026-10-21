"""Independent full-file and per-producer sample acceptance of corrected spans."""
from common import *
import numpy as np,collections
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_semantic_20261016_v2'

def main():
    setup('vlm_semantic_v2/cache_accept');os.nice(10)
    while not (SEM/'CACHE_COMPLETE.json').exists():time.sleep(30)
    complete=read(SEM/'CACHE_COMPLETE.json');assert complete['status']=='PASS'
    assert complete['cases']==103288 and len(complete['cells'])==64
    cells={c['cell']:c for c in complete['cells']};assert len(cells)==64
    arrays={};checks=[]
    for cell,p in cells.items():
        path=ROOT/p['path'];assert sha(path)==p['sha256'];x=np.load(path,mmap_mode='r')
        assert list(x.shape)==p['shape'] and x.shape[0]==103288 and x.dtype==np.float32
        assert np.isfinite(x).all()
        constant=bool(np.array_equal(x,np.broadcast_to(x[0],x.shape)))
        if 'constant_across_cases' in p:assert constant==p['constant_across_cases']
        arrays[cell]=x;checks.append(dict(cell=cell,sha256=p['sha256'],shape=p['shape'],constant_across_cases=constant,source_metadata_has_constant_flag='constant_across_cases' in p))
    receipts=list((BASE/'receipts').glob('*.json'));assert len(receipts)==6456
    groups=collections.defaultdict(list)
    for path in receipts:
        r=read(path);groups[r['rank']].append((r['time'],path,r))
    panel=read(BASE/'panel.json');samples=[];seen=set()
    for rank,values in sorted(groups.items()):
        chosen=[sorted(values)[0],sorted(values)[-1]]
        for _,path,proof in chosen:
            if path.name in seen:continue
            seen.add(path.name);rp=BASE/'results'/path.name;assert sha(rp)==proof['result_sha256'];result=read(rp)
            source=ROOT/result['array_path'];assert sha(source)==result['array_sha256']
            task=result['task'];expected=panel[task['start']:task['end']]
            assert [r['token'] for r in result['records']]==[r['token'] for r in expected]
            with np.load(source) as raw:
                indices=raw['global_indices'];assert np.array_equal(indices,[r['global_index'] for r in expected])
                for cell,metadata in cells.items():
                    block=metadata['block'];j=metadata['group_index']
                    assert np.array_equal(arrays[cell][indices],raw[block][:,j,:]),(rank,cell)
            assert all(r['boundaries']['command_tokens']>0 and r['boundaries']['requirements_tokens']>0 for r in result['records'])
            samples.append(dict(rank=rank,task=task['id'],cases=len(expected),source_sha256=result['array_sha256']))
    atomic(SEM/'CACHE_ACCEPTANCE.json',dict(status='PASS',time=stamp(),cases=103288,cells=64,all_cell_hashes_shapes_and_finite_values_verified=True,
        complete_cache_sha256=sha(SEM/'CACHE_COMPLETE.json'),cell_checks=checks,samples=samples,
        actual_producer_ranks=sorted(groups),sample_cases=sum(r['cases'] for r in samples),all_64_pools_exact_in_each_sample=True,
        code_sha256=sha(Path(__file__)),no_data_model_or_analysis_result_changed=True))
    print('CORRECTED_64_CELL_INDEPENDENT_CACHE_ACCEPTANCE_PASS',len(samples),sum(r['cases'] for r in samples),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        import traceback
        atomic(VOUT/'failures/semantic_cache_accept.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
