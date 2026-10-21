"""One additional model, exact golden admission, then bounded useful work.

The trial exits naturally after committing its fixed number of ordinary
scientific chunks. Existing workers, queues and frozen evaluators are untouched.
"""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import socket
import traceback


def main(a):
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == str(a.device)
    setup('bounded_concurrency/' + a.trial); compatibility()
    import torch
    from vlm_intervene_v4 import Engine
    from r3_runtime import init_scorer
    from r3_first42_rollout_v2 import run as evaluate

    node = next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-') and a.device in node['devices']
    dest = ROOT/'runs/concurrency_trials_v1'/a.trial
    assert not (dest/'PASS.json').exists() and not (dest/'COMPLETE.json').exists()
    free,total = torch.cuda.mem_get_info()
    meta = dict(node=a.node, job=node['job'], hostname=socket.gethostname(), pid=os.getpid(),
                device=str(a.device), lane=a.lane, bounded_trial=True)
    atomic(dest/'LIVE.json',dict(status='PREFLIGHT',time=stamp(),worker=meta,free_bytes=free,total_bytes=total))
    # Same conservative headroom used for the previously admitted extra lanes.
    assert free > 32*(1<<30), 'Insufficient conservative headroom for another model'
    evaluation_hash = sha(ROOT/'code/r3_first42_rollout_v2.py')
    stage=ROOT/'runs'/a.stage; pack=ROOT/'manifests/first42_v1.json'; rows=BATCH1/'manifests/natural_s0.json'
    engine=Engine(); completed=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        engineering=dict(id=a.trial+'_engineering',stage=str((dest/'engineering').relative_to(ROOT)),
                         indices=[60,1],pack=str(pack),pack_sha256=sha(pack),rows=str(rows),
                         rows_sha256=sha(rows),cohort='navtrain',seeds=[0,1,2,3,4])
        result=evaluate(engine,engineering,pool)
        for ref in read(ROOT/result['path'])['cases']:
            actual=read(ROOT/ref['path']); golden=read(ROOT/'runs/first42_engineering_v2/cases'/actual['token']/'RESULT.json')
            assert actual['records']==golden['records'] and actual['selection']==golden['selection']
        atomic(dest/'PASS.json',dict(status='PASS_42X5_GOLDEN_EXACT',time=stamp(),worker=meta,result=result,
                                   evaluation_sha256=evaluation_hash,scientific_chunks=a.chunks))
        tasks=read(stage/'tasks.json'); live=stage/'workers'/(meta['hostname']+'_'+str(meta['pid'])+'.json')
        for task in tasks:
            if len(completed)>=a.chunks:break
            receipt=stage/'receipts'/(task['id']+'.json')
            if receipt.exists():continue
            claim=stage/'claims'/task['id'];claim.parent.mkdir(parents=True,exist_ok=True)
            try:claim.mkdir()
            except FileExistsError:continue
            worker=dict(meta,lease='bounded_'+a.trial)
            atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,task=task))
            atomic(live,dict(status='COMPUTING',time=stamp(),worker=worker,task=task['id'],completed=len(completed)))
            began=time.monotonic()
            try:
                assert sha(ROOT/'code/r3_first42_rollout_v2.py')==evaluation_hash
                result=evaluate(engine,task,pool)
                atomic(receipt,dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result,seconds=time.monotonic()-began))
            except BaseException as error:
                atomic(stage/'failures'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=worker,
                       task=task,error=repr(error),traceback=traceback.format_exc()))
                raise
            completed.append(task['id'])
            atomic(dest/'LIVE.json',dict(status='COMPUTING',time=stamp(),worker=meta,completed=completed))
        engine.verify_engine()
        atomic(live,dict(status='BOUNDED_TRIAL_FINISHED',time=stamp(),worker=meta,completed=len(completed)))
    atomic(dest/'COMPLETE.json',dict(status='COMPLETE_NATURAL_EXIT',time=stamp(),worker=meta,
           completed_tasks=completed,evaluation_sha256=evaluation_hash,no_existing_workers_signalled=True))
    print(json.dumps(dict(event='BOUNDED_CONCURRENCY_TRIAL_COMPLETE',trial=a.trial,chunks=len(completed))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--device',type=int,required=True)
    p.add_argument('--lane',type=int,required=True);p.add_argument('--trial',required=True)
    p.add_argument('--stage',default='first42_navtrain_v1');p.add_argument('--chunks',type=int,default=8)
    a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/concurrency_trials_v1'/a.trial/'FAILED.json',dict(status='FAILED',time=stamp(),
               error=repr(error),traceback=traceback.format_exc()))
        raise
