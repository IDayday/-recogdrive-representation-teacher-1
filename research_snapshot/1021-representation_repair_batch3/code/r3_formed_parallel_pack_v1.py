"""Stress one largest formed pack on all retained model lanes, then wait.

Uses the original admitted scientific evaluator and actual DSW engineering
golden outputs. No extra models, cloud calls or changes to existing methods.
"""
from r3_common import *
import socket
import traceback


def run(engine,parent,pool):
    import numpy as np
    import torch
    from r3_formed_rollout_v1 import run as evaluate
    from r3_formed_audit_v1 import audit
    stage=ROOT/parent['stage'];config_path=stage/'CONFIG.json'
    assert sha(config_path)==parent['configuration_sha256'];config=read(config_path)
    node=next(n for n in config['nodes'] if socket.gethostname().startswith(n['job']+'-'))
    device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices']
    key=node['name']+'_device%02d_pid%d'%(device,os.getpid());folder=stage/'workers'/key
    if not (folder/'PASS.json').exists():
        claimed=stage/'claims'/key;claimed.parent.mkdir(parents=True,exist_ok=True)
        try:
            claimed.mkdir()
            atomic(claimed/'OWNER.json',dict(time=stamp(),hostname=socket.gethostname(),pid=os.getpid(),node=node['name'],device=device))
            pack=read(config['pack']);rows=BATCH1/'manifests/natural_s0.json';prior=ROOT/'analysis/first42_engineering_v2/SUMMARY.json'
            task=dict(id=key,stage=str(folder.relative_to(ROOT)),pack=config['pack'],pack_sha256=config['pack_sha256'],
                rows=str(rows),rows_sha256=sha(rows),indices=[60,1],seeds=[0,1,2,3,4],cohort='navtrain',engineering=True,
                first42_summary=str(prior),first42_summary_sha256=sha(prior))
            result=evaluate(engine,task,pool);proof=audit(ROOT/result['path'])
            for case in read(ROOT/result['path'])['cases']:
                actual=read(ROOT/case['path']);gold=read(ROOT/config['golden_stage']/'cases'/actual['token']/'RESULT.json')
                for group in ['numeric','interfaces']:
                    with np.load(ROOT/actual[group]['path'],allow_pickle=False) as a,np.load(ROOT/gold[group]['path'],allow_pickle=False) as b:
                        assert set(a.files)==set(b.files)
                        for name in a.files:assert np.array_equal(a[name],b[name]),(group,name)
                assert actual['selection']==gold['selection']
            free,total=torch.cuda.mem_get_info()
            atomic(folder/'PASS.json',dict(status='PASS_FULL_PACK_ALL_FIVE_EXACT_GOLDEN_AND_CPU_AUDIT',time=stamp(),
                node=node['name'],device=device,pid=os.getpid(),result=result,audit=proof,
                current_device_free_bytes=free,device_total_bytes=total,peak_process_cuda_allocated_bytes=torch.cuda.max_memory_allocated()))
        except BaseException as error:
            atomic(stage/'failures'/(key+'.json'),dict(status='FAILED',time=stamp(),node=node['name'],device=device,pid=os.getpid(),
                error=repr(error),traceback=traceback.format_exc()))
            raise
    began=time.monotonic()
    while True:
        failed=next((stage/'failures').glob('*.json'),None)
        if failed:return dict(status='FAILED_REQUIRES_AGENT_REVIEW',path=str(failed))
        passes=[read(p) for p in (stage/'workers').glob('*/PASS.json')]
        counts={(n['name'],d):0 for n in config['nodes'] for d in n['devices']}
        for p in passes:counts[p['node'],p['device']]+=1
        assert max(counts.values(),default=0)<=config['lanes_per_device']
        if counts and all(v==config['lanes_per_device'] for v in counts.values()):
            complete=stage/'ALL_LANES_READY.json'
            if not complete.exists():atomic(complete,dict(status='ALL_RETAINED_LANES_READY_REQUIRES_AGENT_REVIEW',time=stamp(),devices=len(counts),lanes=len(passes)))
            return dict(status='ENGINEERING_ALL_LANES_READY',devices=len(counts),lanes=len(passes))
        if time.monotonic()-began>1800:raise TimeoutError('Full-pack lane checklist did not finish within 30 minutes')
        time.sleep(10)
