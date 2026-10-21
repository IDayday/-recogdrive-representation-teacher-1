"""Cache seven tie-break edit sizes from audited first42 records, CPU only.

This is a numeric analysis cache, not a new teacher extraction or snapshot.
The R3 size is calculated using S0-S2 only. Existing selection never changes.
"""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import multiprocessing as mp


def initialize():setup('selection_edit_cache/'+str(os.getpid()),threads=1)


def read_edits(arguments):
    import numpy as np
    index,reference,ids,choice=arguments
    path=ROOT/reference['path'];raw=retry(path.read_bytes);assert hashlib.sha256(raw).hexdigest()==reference['sha256'];record=json.loads(raw)
    assert record['global_index']==index and record['token']==reference['token'] and record['status']=='COMPLETE'
    lookup={(r['arm'],r['seed_index']):r for r in record['records']};assert len(lookup)==210
    assert record['selection']['R1']==[dict(arm=ids[choice[j]],seed_index=j) for j in range(5)]
    assert record['selection']['R2']==[dict(arm=ids[choice[5]],seed_index=j) for j in range(5)]
    assert record['selection']['R3']==[dict(arm=ids[choice[6]],seed_index=j) for j in [3,4]]
    values=np.asarray([lookup[ids[choice[j]],j]['relative_edit'] for j in range(5)]+
        [np.mean([lookup[ids[choice[5]],j]['relative_edit'] for j in range(5)]),
         np.mean([lookup[ids[choice[6]],j]['relative_edit'] for j in range(3)])],dtype=np.float64)
    assert values.shape==(7,) and np.isfinite(values).all() and (values>=0).all()
    assert all(values[j]==0 for j in range(7) if ids[choice[j]]=='Base')
    return index,record['token'],values


def main(a):
    setup('selection_edit_cache_main/'+a.cohort,threads=1)
    import numpy as np
    source=ROOT/'analysis'/('first42_'+a.cohort+'_v1')/'SUMMARY.json';summary=read(source)
    assert summary['status']=='PASS_COMPLETE_AUDITED_FIRST42'
    path=ROOT/summary['artifacts']['CASE_INDEX.json']['path'];assert sha(path)==summary['artifacts']['CASE_INDEX.json']['sha256'];references=read(path)
    assert [r['global_index'] for r in references]==list(range(summary['cases']))
    selected=np.load(ROOT/summary['artifacts']['selected.npy']['path'],mmap_mode='r',allow_pickle=False)
    ids=[r['id'] for r in read(ROOT/'manifests/first42_v1.json')['entries']];assert len(ids)==42
    indices=[int(v) for v in a.indices.split(',')] if a.indices else list(range(summary['cases']))
    assert len(indices)==len(set(indices)) and set(indices)<=set(range(summary['cases']))
    target=ROOT/a.output;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
    work=target.with_name('.'+target.name+'.building_'+uuid.uuid4().hex);work.mkdir()
    output=np.lib.format.open_memmap(work/'selected_edits.npy',mode='w+',dtype=np.float64,shape=(len(indices),7))
    mapping={index:position for position,index in enumerate(indices)};seen=set();pending={};cursor=iter(indices)
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        while True:
            while len(pending)<a.workers*4:
                index=next(cursor,None)
                if index is None:break
                future=pool.submit(read_edits,(index,references[index],ids,selected[index].tolist()));pending[future]=index
            if not pending:break
            ready,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in ready:
                expected=pending.pop(future);index,token,values=future.result();assert index==expected and token==references[index]['token'] and index not in seen
                output[mapping[index]]=values;seen.add(index)
            if len(seen)%500<32:
                atomic(work/'LIVE.json',dict(status='RUNNING',time=stamp(),complete_cases=len(seen),expected_cases=len(indices),workers=a.workers))
    assert seen==set(indices);output.flush();atomic(work/'INDICES.json',indices)
    proof=dict(status='PASS_FIRST42_SELECTED_EDIT_ANALYSIS_CACHE',time=stamp(),cohort=a.cohort,cases=len(indices),complete_population=not a.indices,
        source_summary=str(source.relative_to(ROOT)),source_summary_sha256=sha(source),case_index_sha256=sha(path),candidate_ids=ids,
        artifacts={name:dict(path=str((target/name).relative_to(ROOT)),sha256=sha(work/name)) for name in ['selected_edits.npy','INDICES.json']},
        R3_size_uses_S0S2_only=True,no_existing_choices_changed=True,new_teacher_snapshot_created=False,GT_used=False)
    atomic(work/'SUMMARY.json',proof);work.rename(target)
    print(json.dumps({k:v for k,v in proof.items() if k not in ['candidate_ids','artifacts']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cohort',choices=['navtrain','navtest'],required=True);p.add_argument('--output',required=True)
    p.add_argument('--indices');p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        import traceback
        atomic(ROOT/'runs/first42_selected_edit_cache_v1'/a.cohort/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
