"""Independent CPU validation and compact numeric shards for student scores."""
from d4_common_v2 import *
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import argparse
import multiprocessing as mp
import socket
import traceback


def initialize():setup('full_evaluation_audit/'+str(os.getpid()),threads=1)


def audit(receipt_path):
    import numpy as np
    from d4_evaluate_student_v1 import population
    from r3_incremental_audit_v1 import FIELDS
    path=Path(receipt_path);receipt=read(path);task=receipt['task']
    assert receipt['status']=='COMPLETE';result_path=Path(receipt['result']['path'])
    assert sha(result_path)==receipt['result']['sha256'];result=read(result_path)
    assert result['status']=='COMPLETE_STUDENT_EVALUATION_CHUNK' and result['task']==task
    rows,prior,_=population(task['cohort']);checked=[];quality=[];baseline=[];trajectories=[];old_teacher=[];mse=[]
    for case in result['cases']:
        record_path=ROOT/case['path'];assert sha(record_path)==case['sha256'];record=read(record_path)
        assert record['status']=='COMPLETE_STUDENT_NATIVE_EVALUATION' and not record['GT_used'] and not record['student_inference_uses_teacher_or_PDMS']
        assert record['checkpoint_sha256']==task['checkpoint_sha256'] and record['training_config_sha256']==task['training_config_sha256']
        assert record['noises']==task['noises'] and record['fields']==FIELDS
        index=record['global_index'];row=rows[index];assert row['token']==record['token'] and row['session']==record['session']
        numeric=ROOT/record['arrays']['path'];assert sha(numeric)==record['arrays']['sha256']
        with np.load(numeric,allow_pickle=False) as z:
            q=np.array(z['student_quality']);b=np.array(z['Base_quality']);t=np.array(z['student_trajectories']);bt=np.array(z['Base_trajectories']);teacher=np.array(z['teacher_R2_reference_S0S4'])
            noises=z['noise_indices'].tolist();assert noises==task['noises'] and q.shape==b.shape==(len(noises),7) and t.shape==bt.shape==(len(noises),8,3)
            assert q.dtype==b.dtype==np.float64 and t.dtype==bt.dtype==np.float32
            assert np.isfinite(q).all() and np.isfinite(b).all() and np.isfinite(t).all() and np.isfinite(bt).all()
            assert z['input_ids'].ndim==1 and z['attention_mask'].shape==z['input_ids'].shape
            assert record['interface']['shape']==[len(z['input_ids']),384]
            for a,j in enumerate(noises):
                if j<5:
                    assert np.array_equal(b[a],prior['scores'][index,0,j]) and np.array_equal(bt[a],prior['trajectories'][index,0,j])
            assert np.array_equal(teacher,prior['scores'][index,int(prior['selected'][index,5])])
        for values in [q,b]:
            assert (values>=0).all() and (values<=1+1e-8).all()
            assert np.max(np.abs(values[:,1]*values[:,2]*(5*values[:,4]+5*values[:,3]+2*values[:,5])/12-values[:,0]))<1e-8
        h=record['interface'];assert len(h['sha256'])==64 and h['same_actual_forward_for_all_student_trajectories']
        assert np.isfinite(h['MSE']) and h['MSE']>=0
        assert h['relative_error'] is None or (np.isfinite(h['relative_error']) and h['relative_error']>=0)
        if any(j>=5 for j in noises):assert record['original_Base_S0_replayed_exactly_when_new_noises']
        if task['cohort']=='navtest':
            lock=read(task['test_lock']);assert sha(task['test_lock'])==task['test_lock_sha256']
            assert lock['status']=='FROZEN_MODEL_BEFORE_TEST' and lock['checkpoint_sha256']==task['checkpoint_sha256']
        checked.append(dict(global_index=index,token=row['token'],session=row['session'],subset=record['subset'],pool=record['pool'],
            record_path=str(record_path.relative_to(ROOT)),record_sha256=case['sha256'],numeric_path=record['arrays']['path'],numeric_sha256=record['arrays']['sha256'],
            student_interface_sha256=h['sha256'],interface_comparison_scope=h['teacher_comparison_scope']))
        quality.append(q);baseline.append(b);trajectories.append(t);old_teacher.append(teacher);mse.append(h['MSE'])
    assert [c['global_index'] for c in checked]==task['indices']
    stage=ROOT/task['output_stage'];output=stage/'audit/shards'/path.name;numeric=output.with_suffix('.npz')
    hashed=save_arrays(numeric,dict(indices=np.asarray(task['indices'],dtype=np.int64),noise_indices=np.asarray(task['noises'],dtype=np.int64),
        student_quality=np.stack(quality),Base_quality=np.stack(baseline),student_trajectories=np.stack(trajectories),teacher_R2_reference_S0S4=np.stack(old_teacher),interface_MSE=np.asarray(mse,dtype=np.float64)))
    proof=dict(status='PASS_INDEPENDENT_STUDENT_EVALUATION_CPU_AUDIT',time=stamp(),receipt_path=str(path.relative_to(ROOT)),receipt_sha256=sha(path),
        task_id=task['id'],checkpoint_sha256=task['checkpoint_sha256'],training_config_sha256=task['training_config_sha256'],noises=task['noises'],
        cases=checked,array=dict(path=str(numeric.relative_to(ROOT)),sha256=hashed))
    atomic(output,proof);return len(checked)


def main(a):
    initialize();assigned=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(assigned['job']+'-')
    pending={};seen={};finished=set();count=0
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        while True:
            for future in [f for f in pending if f.done()]:
                receipt,stage=pending.pop(future)
                try:count+=future.result()
                except BaseException as error:
                    atomic(stage/'audit/failures'/receipt.name,dict(status='FAILED',time=stamp(),node=a.node,error=repr(error),traceback=traceback.format_exc()));raise
            queue=ROOT/'runs/EVALUATION_QUEUE.json';stages=read(queue)['stages'] if queue.exists() else []
            for setting in sorted(stages,key=lambda x:(x['priority'],x['id'])):
                if setting['kind']!='formal' or setting['group']!=assigned['group']:continue
                stage=ROOT/setting['stage'];key=str(stage)
                if key in finished:continue
                if (stage/'AUDIT_COMPLETE.json').exists():finished.add(key);continue
                if not (stage/'receipts').exists():continue
                spec=read(stage/'SPECIFICATION.json');total=(spec['case_count']+spec['chunk_size']-1)//spec['chunk_size']
                receipts=list((stage/'receipts').glob('*.json'))
                if len(receipts)==total and not (stage/'COMPUTE_COMPLETE.json').exists():
                    atomic(stage/'COMPUTE_COMPLETE.json',dict(status='ALL_GPU_CHUNKS_PRESENT_REQUIRES_AUDIT',time=stamp(),chunks=total))
                if len(list((stage/'audit/shards').glob('*.json')))==total:
                    atomic(stage/'AUDIT_COMPLETE.json',dict(status='ALL_STUDENT_CHUNKS_AUDITED_REQUIRES_ACCEPTANCE',time=stamp(),chunks=total));finished.add(key);continue
                visited=seen.setdefault(key,set())
                for receipt in receipts:
                    if len(pending)>=a.workers*2:break
                    if receipt.name in visited:continue
                    visited.add(receipt.name)
                    if (stage/'audit/shards'/receipt.name).exists():continue
                    claim=stage/'audit/claims'/receipt.stem;claim.parent.mkdir(parents=True,exist_ok=True)
                    try:claim.mkdir()
                    except FileExistsError:continue
                    atomic(claim/'OWNER.json',dict(time=stamp(),pid=os.getpid(),node=a.node,receipt=str(receipt)))
                    pending[pool.submit(audit,str(receipt))]=(receipt,stage)
            atomic(ROOT/'runs/evaluation_audit_workers'/(a.node+'.json'),dict(status='RUNNING',time=stamp(),node=a.node,pid=os.getpid(),audited_cases=count,pending=len(pending),finished_stages=len(finished)))
            if pending:wait(pending,timeout=10,return_when=FIRST_COMPLETED)
            else:time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=4);main(p.parse_args())
