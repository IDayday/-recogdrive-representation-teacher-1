"""Retained CPU auditors for appended compact stages; no scientific choices."""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import multiprocessing as mp
import socket
import traceback


def initialize():setup('formed_cpu_audit/'+socket.gethostname()+'/'+str(os.getpid()),threads=1)


def check(arguments):
    from r3_formed_audit_v1 import audit
    receipt_path,stage_path=map(Path,arguments)
    receipt=read(receipt_path);assert receipt['status']=='COMPLETE'
    result_path=ROOT/receipt['result']['path']
    assert sha(result_path)==receipt['result']['sha256']
    proof=audit(result_path)
    assert proof['status']=='PASS_GENERIC_CPU_AUDIT'
    assert [r['global_index'] for r in proof['checks']]==receipt['task']['indices']
    proof.update(receipt=str(receipt_path.relative_to(ROOT)),receipt_sha256=sha(receipt_path))
    output=stage_path/'audit_v1/shards'/receipt_path.name
    assert not output.exists();atomic(output,proof)
    return dict(cases=len(proof['checks']),proof=str(output.relative_to(ROOT)))


def main(a):
    initialize();registry=read(ROOT/'resources/REGISTRY.json')
    node=next(v for v in registry['nodes'] if v['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    live=ROOT/'runs/elastic_audit_workers'/(a.node+'_'+str(os.getpid())+'.json')
    queue_path=ROOT/'runs/ELASTIC_STAGE_QUEUE.json';pending={};seen={};completed=set();count=0
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        while True:
            for future in [v for v in pending if v.done()]:
                receipt,stage=pending.pop(future)
                try:future.result();count+=1
                except BaseException as error:
                    atomic(stage/'audit_v1/failures'/receipt.name,dict(status='FAILED',time=stamp(),node=a.node,
                        receipt=str(receipt),error=repr(error),traceback=traceback.format_exc()))
                    raise
            queue=read(queue_path) if queue_path.exists() else dict(stages=[])
            for setting in sorted(queue['stages'],key=lambda v:(v['priority'],v['id'])):
                stage=ROOT/setting['stage'];key=str(stage)
                if key in completed:continue
                if (stage/'AUDIT_COMPLETE.json').exists():completed.add(key);continue
                if not (stage/'receipts').exists():continue
                receipts=list((stage/'receipts').glob('*.json'))
                spec=read(stage/'SPECIFICATION.json');expected=(spec['case_count']+spec['chunk_size']-1)//spec['chunk_size']
                if len(receipts)==expected and not (stage/'COMPUTE_COMPLETE.json').exists():
                    atomic(stage/'COMPUTE_COMPLETE.json',dict(status='ALL_COMPUTE_RECEIPTS_PRESENT_REQUIRES_ACCEPTANCE',time=stamp(),chunks=expected))
                if len(list((stage/'audit_v1/shards').glob('*.json')))==expected:
                    atomic(stage/'AUDIT_COMPLETE.json',dict(status='ALL_CHUNKS_CPU_AUDITED_REQUIRES_ACCEPTANCE',time=stamp(),chunks=expected))
                    completed.add(key);continue
                visited=seen.setdefault(key,set())
                for receipt in receipts:
                    if len(pending)>=a.workers*2:break
                    if receipt.name in visited:continue
                    visited.add(receipt.name)
                    if (stage/'audit_v1/shards'/receipt.name).exists():continue
                    claim=stage/'audit_v1/claims'/receipt.stem;claim.parent.mkdir(parents=True,exist_ok=True)
                    try:retry(lambda:claim.mkdir())
                    except FileExistsError:continue
                    atomic(claim/'OWNER.json',dict(time=stamp(),node=a.node,pid=os.getpid(),hostname=socket.gethostname(),receipt=str(receipt)))
                    pending[pool.submit(check,(str(receipt),str(stage)))]=(receipt,stage)
            atomic(live,dict(status='RUNNING',time=stamp(),pid=os.getpid(),node=a.node,
                audited_chunks=count,pending=len(pending),completed_stages=len(completed)))
            if pending:wait(pending,timeout=10,return_when=FIRST_COMPLETED)
            else:time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=2)
    p.add_argument('--interval',type=int,default=60);main(p.parse_args())
