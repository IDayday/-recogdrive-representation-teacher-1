"""Accept audited full formed packs; retain all scores and compact actual winners.

This merges existing results only. It neither selects new candidate definitions,
freezes a teacher snapshot, nor releases any resource. Local-pack statistics are
explicitly distinct from the later union with first42 and other admitted packs.
"""
from r3_common import *
import argparse
import math


def finish(stage,spec,proof_paths,engineering=False):
    import numpy as np
    from r3_finish42_v1 import summarize
    task=spec['task_template'];pack_path=Path(task['pack']);assert sha(pack_path)==task['pack_sha256'];pack=read(pack_path)
    ids=['Base']+[v['id'] for v in pack['entries']];assert len(ids)==len(set(ids))
    assert sha(task['rows'])==task['rows_sha256'];all_rows=read(task['rows'])
    expected=read(spec['indices_path']) if 'indices_path' in spec else list(range(spec['case_count']))
    if 'indices_path' in spec:assert sha(spec['indices_path'])==spec['indices_sha256']
    assert len(expected)==spec['case_count'] and len(set(expected))==len(expected)
    rows=[all_rows[i] for i in expected];mapping={index:position for position,index in enumerate(expected)};count=len(expected)
    summary_path=Path(task['first42_summary']);assert sha(summary_path)==task['first42_summary_sha256'];first42=read(summary_path)
    base=np.load(ROOT/first42['artifacts']['scores.npy']['path'],mmap_mode='r',allow_pickle=False)
    target=ROOT/'analysis'/('formed_merge_engineering_v1' if engineering else 'formed_full_v1')/stage.name
    assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
    work=target.with_name('.'+target.name+'.building_'+uuid.uuid4().hex);work.mkdir()
    arrays={
        'scores.npy':np.lib.format.open_memmap(work/'scores.npy',mode='w+',dtype=np.float64,shape=(count,len(ids),5,7)),
        'selected.npy':np.lib.format.open_memmap(work/'selected.npy',mode='w+',dtype=np.int64,shape=(count,7)),
        'selected_edits.npy':np.lib.format.open_memmap(work/'selected_edits.npy',mode='w+',dtype=np.float64,shape=(count,7)),
        'winner_trajectories.npy':np.lib.format.open_memmap(work/'winner_trajectories.npy',mode='w+',dtype=np.float32,shape=(count,3,5,8,3))}
    seen=np.zeros(count,dtype=bool);sources=[];index_rows=[None]*count
    assert len(proof_paths)==math.ceil(count/spec['chunk_size'])
    for proof_path in sorted(proof_paths):
        proof=read(proof_path);assert proof['status']=='PASS_GENERIC_CPU_AUDIT' and proof['all_branches_and_three_choices_verified']
        assert proof['all_competitive_actual_targets_present'] and proof['no_GT_used']
        result_path=ROOT/proof['result_path'];assert sha(result_path)==proof['result_sha256'];result=read(result_path)
        result_task=result['task'];assert result_task['pack_sha256']==task['pack_sha256'] and result_task['rows_sha256']==task['rows_sha256']
        assert result_task['seeds']==[0,1,2,3,4] and result_task['first42_summary_sha256']==task['first42_summary_sha256']
        if not engineering:
            receipt_path=ROOT/proof['receipt'];assert sha(receipt_path)==proof['receipt_sha256'];receipt=read(receipt_path)
            assert receipt['status']=='COMPLETE' and receipt['task']==result_task
            assert receipt['result']['sha256']==proof['result_sha256']
        assert [c['global_index'] for c in result['cases']]==result_task['indices']==[c['global_index'] for c in proof['checks']]
        for reference,check in zip(result['cases'],proof['checks']):
            path=ROOT/reference['path'];assert sha(path)==reference['sha256'];record=read(path);index=record['global_index'];position=mapping[index]
            assert not seen[position] and record['token']==rows[position]['token'] and record['session']==rows[position]['session']
            assert record['candidate_ids']==ids and record['pack_sha256']==task['pack_sha256'] and record['seeds']==[0,1,2,3,4]
            numeric=ROOT/record['numeric']['path'];assert sha(numeric)==record['numeric']['sha256']
            with np.load(numeric,allow_pickle=False) as z:
                q=np.asarray(z['scores']);trajectory=np.asarray(z['trajectories']);edits=np.asarray(z['relative_edits'])
                choice=np.asarray(check['selection'],dtype=np.int64)
                assert q.shape==(len(ids),5,7) and trajectory.shape==(len(ids),5,8,3) and edits.shape==(len(ids),5)
                assert np.array_equal(q[0],base[index,0]) and choice.shape==(7,) and np.isfinite(q).all() and np.isfinite(edits).all()
                arrays['scores.npy'][position]=q;arrays['selected.npy'][position]=choice
                arrays['selected_edits.npy'][position]=[edits[choice[j],j] for j in range(5)]+[edits[choice[5]].mean(),edits[choice[6],:3].mean()]
                arrays['winner_trajectories.npy'][position,0]=np.stack([trajectory[choice[j],j] for j in range(5)])
                arrays['winner_trajectories.npy'][position,1]=trajectory[choice[5]];arrays['winner_trajectories.npy'][position,2]=trajectory[choice[6]]
            seen[position]=True;index_rows[position]=dict(global_index=index,token=record['token'],session=record['session'],subset=record['subset'],
                record=str(path.relative_to(ROOT)),record_sha256=reference['sha256'],numeric=record['numeric'],interfaces=record['interfaces'])
        sources.append(dict(path=str(proof_path.relative_to(ROOT)),sha256=sha(proof_path)))
    assert seen.all()
    for array in arrays.values():array.flush()
    groups={'navtrain_all' if count==103288 and task['cohort']=='navtrain' else 'navtest' if task['cohort']=='navtest' else 'engineering':list(range(count))}
    if task['cohort']=='navtrain':
        for subset in ['exploration','validation']:
            ix=[i for i,row in enumerate(rows) if row['subset']==subset]
            if ix:groups[subset]=ix
    statistics={name:summarize(arrays['scores.npy'],arrays['selected.npy'],rows,indices) for name,indices in groups.items()}
    atomic(work/'CASE_INDEX.json',index_rows)
    artifacts={name:dict(path=str((target/name).relative_to(ROOT)),sha256=sha(work/name)) for name in list(arrays)+['CASE_INDEX.json']}
    summary=dict(status='PASS_ENGINEERING_FORMED_MERGE' if engineering else 'PASS_COMPLETE_AUDITED_FORMED_PACK',time=stamp(),stage=str(stage.relative_to(ROOT)),
        cohort=task['cohort'],cases=count,entries=len(ids),candidate_ids=ids,pack=str(pack_path),pack_sha256=task['pack_sha256'],
        rows=task['rows'],rows_sha256=task['rows_sha256'],seeds=[0,1,2,3,4],artifacts=artifacts,sources=sources,results=statistics,
        selection_scope='This formed pack plus Base only; not the union with first42 or other packs',
        union_live_best_update_required=True,teacher_snapshot_frozen=False,GT_used=False,
        R3_selection_uses_S0S2_only=True,R3_S3S4_negative_results_retained=True,no_extra_safety_filter=True)
    atomic(work/'SUMMARY.json',summary);work.rename(target)
    if not engineering:
        accepted=stage/'AGENT_ACCEPTANCE.json';assert not accepted.exists()
        atomic(accepted,dict(status=summary['status'],time=stamp(),summary=str((target/'SUMMARY.json').relative_to(ROOT)),summary_sha256=sha(target/'SUMMARY.json'),
            live_best_union_update_still_required=True,no_teacher_snapshot_created=True))
    print(json.dumps(dict(status=summary['status'],cases=count,entries=len(ids),results={name:{k:round(v['PDMS'],6) for k,v in value['endpoints'].items()} for name,value in statistics.items()})),flush=True)


def main(a):
    setup('formed_merge/'+Path(a.stage).name,threads=4)
    stage=ROOT/a.stage
    if a.engineering:
        proof=stage/'AUDIT.json';result=read(ROOT/read(proof)['result_path']);task=result['task']
        indices=ROOT/'manifests/formed_merge_engineering_indices_v1.json'
        if indices.exists():assert read(indices)==task['indices']
        else:atomic(indices,task['indices'])
        spec=dict(case_count=len(task['indices']),chunk_size=len(task['indices']),task_template=task,indices_path=str(indices),indices_sha256=sha(indices))
        finish(stage,spec,[proof],engineering=True)
    else:
        assert (stage/'AUDIT_COMPLETE.json').exists() and not (stage/'AGENT_ACCEPTANCE.json').exists()
        assert not list((stage/'failures').glob('*.json')) and not list((stage/'audit_v1/failures').glob('*.json'))
        spec=read(stage/'SPECIFICATION.json');assert spec['case_count']==(103288 if spec['task_template']['cohort']=='navtrain' else 12146)
        finish(stage,spec,list((stage/'audit_v1/shards').glob('*.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--engineering',action='store_true');main(p.parse_args())
