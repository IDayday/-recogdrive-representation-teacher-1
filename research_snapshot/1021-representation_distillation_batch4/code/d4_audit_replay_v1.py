"""Independent streaming CPU audit of full-context same-execution teachers."""
from d4_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import multiprocessing as mp
import socket
import traceback


def initialize():setup('replay_audit/'+socket.gethostname()+'/'+str(os.getpid()),threads=1)


def check(receipt_path):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    receipt_path=Path(receipt_path);receipt=read(receipt_path)
    assert receipt['status']=='COMPLETE'
    result_path=Path(receipt['result']['path']);assert sha(result_path)==receipt['result']['sha256']
    result=read(result_path);assert result['status']=='COMPLETE_FULL_CONTEXT_REPLAY'
    checked=[]
    for ref in result['cases']:
        path=ROOT/ref['path'];assert sha(path)==ref['sha256'];record=read(path)
        assert record['status']=='PASS_EXACT_R2_FULL_CONTEXT_REPLAY' and not record['GT_used']
        for name in ['same_execution_interface','all_five_trajectories_exact','all_five_fresh_scores_exact','valid_interface_exact','teacher_fixed_not_reselected']:assert record[name]
        old_path=B3/record['source_record'];assert sha(old_path)==record['source_record_sha256'];old=read(old_path)
        ident=record['candidate'];assert old['selection']['R2']==[dict(arm=ident,seed_index=j) for j in range(5)]
        lookup={(r['arm'],r['seed_index']):r for r in old['records']}
        array=ROOT/record['arrays']['path'];assert sha(array)==record['arrays']['sha256']
        with np.load(array,allow_pickle=False) as z:
            h=z['teacher_interface'];t=z['teacher_trajectories'];q=z['teacher_quality'];ids=z['input_ids'];mask=z['attention_mask'];pos=z['position_ids'];valid=z['valid_token_positions']
            assert h.dtype==np.float32 and h.shape==(len(ids),384) and t.shape==(5,8,3) and q.shape==(5,7)
            assert np.isfinite(h).all() and np.isfinite(t).all() and np.isfinite(q).all()
            assert len(ids)==record['full_tokens'] and np.array_equal(np.flatnonzero(mask),valid)
            assert len(valid)==record['valid_tokens'] and int((mask==0).sum())==record['padding_tokens']
            expected=np.cumsum(mask,dtype=np.int64)-1;expected[mask==0]=1;assert np.array_equal(expected,pos)
            assert hashlib.sha256(h.tobytes()).hexdigest()==record['teacher_interface_sha256']
            valid_hash=hashlib.sha256(h[valid].tobytes()).hexdigest()
            for j in range(5):
                r=lookup[ident,j]
                assert r['seed']==seed(record['token'],j) and r['interface_sha256']==valid_hash
                assert np.array_equal(t[j],np.asarray(r['trajectory'],dtype=np.float32))
                assert q[j].tolist()==[r['score'][f] for f in FIELDS]
            assert np.max(np.abs(q[:,1]*q[:,2]*(5*q[:,4]+5*q[:,3]+2*q[:,5])/12-q[:,0]))<1e-8
        checked.append(dict(global_index=record['global_index'],token=record['token'],record_sha256=ref['sha256'],arrays_sha256=record['arrays']['sha256'],full_tokens=record['full_tokens'],padding_tokens=record['padding_tokens']))
    assert [c['global_index'] for c in checked]==receipt['task']['indices']
    proof=dict(status='PASS_INDEPENDENT_FULL_CONTEXT_CPU_AUDIT',time=stamp(),receipt_sha256=sha(receipt_path),result_sha256=sha(result_path),cases=checked)
    target=ROOT/'runs/full_context_replay_v1/audit/shards'/receipt_path.name;assert not target.exists();atomic(target,proof)
    return len(checked)


def main(a):
    initialize();config=read(ROOT/'configs/REPLAY_SERVICE_V1.json');node=next(n for n in config['nodes'] if n['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    stage=ROOT/'runs/full_context_replay_v1';pending={};seen=set();count=0
    total=(config['case_count']+config['chunk_size']-1)//config['chunk_size']
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        while True:
            for future in [f for f in pending if f.done()]:
                receipt=pending.pop(future)
                try:count+=future.result()
                except BaseException as error:
                    atomic(stage/'audit/failures'/receipt.name,dict(status='FAILED',time=stamp(),node=a.node,error=repr(error),traceback=traceback.format_exc()));raise
            for receipt in (stage/'receipts').glob('*.json'):
                if len(pending)>=a.workers*2:break
                if receipt.name in seen:continue
                seen.add(receipt.name)
                if (stage/'audit/shards'/receipt.name).exists():continue
                claim=stage/'audit/claims'/receipt.stem;claim.parent.mkdir(parents=True,exist_ok=True)
                try:claim.mkdir()
                except FileExistsError:continue
                atomic(claim/'OWNER.json',dict(time=stamp(),node=a.node,pid=os.getpid(),hostname=socket.gethostname()))
                pending[pool.submit(check,str(receipt))]=receipt
            atomic(stage/'audit/workers'/(a.node+'.json'),dict(status='RUNNING',time=stamp(),pid=os.getpid(),node=a.node,pending=len(pending),audited_cases=count))
            if len(list((stage/'audit/shards').glob('*.json')))==total:
                atomic(stage/'audit'/('NODE_COMPLETE_'+a.node+'.json'),dict(status='COMPLETE',time=stamp(),node=a.node))
                print(json.dumps(dict(event='FULL_CONTEXT_CPU_AUDIT_COMPLETE',node=a.node)),flush=True);return
            if pending:wait(pending,timeout=10,return_when=FIRST_COMPLETED)
            else:time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=4);main(p.parse_args())
