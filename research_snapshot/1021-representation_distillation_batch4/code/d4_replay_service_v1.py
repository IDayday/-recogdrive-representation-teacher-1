"""Serve selected-branch replay on allocated retained nodes, without GT."""
from d4_common import *
import socket
import traceback


def run(engine,parent,pool):
    from d4_replay_teacher_v1 import run as evaluate
    config_path=ROOT/'configs/REPLAY_SERVICE_V1.json';config=read(config_path)
    assert sha(config_path)==parent['batch4_configuration_sha256']
    candidates=[n for n in config['nodes'] if socket.gethostname().startswith(n['job']+'-')]
    if not candidates:return dict(status='NODE_NOT_ASSIGNED_TO_BATCH4_REPLAY')
    node=candidates[0];device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices']
    stage=ROOT/'runs/full_context_replay_v1';engineering=ROOT/'runs/replay_multidevice_v1'
    key=node['name']+'_device%02d'%device;folder=engineering/key;claim=folder/'CLAIM'
    claim.parent.mkdir(parents=True,exist_ok=True);owner=False
    try:claim.mkdir();owner=True
    except FileExistsError:pass
    if owner:
        try:
            task=dict(config['task_template'],id=key,indices=config['smoke_indices'],output_stage=str(folder.relative_to(ROOT)))
            result=evaluate(engine,task,pool)
            for case in read(result['path'])['cases']:
                actual=read(ROOT/case['path']);gold=read(ROOT/'runs/teacher_replay_smoke_v1/cases'/actual['token']/'RESULT.json')
                assert actual['teacher_interface_sha256']==gold['teacher_interface_sha256']
                for name in ['full_tokens','valid_tokens','padding_tokens','candidate','teacher_residual_squared_sum','Base_interface_squared_sum']:
                    assert actual[name]==gold[name]
            atomic(folder/'PASS.json',dict(status='PASS_R2_FULL_CONTEXT_DEVICE_EXACT',time=stamp(),node=node['name'],device=device,pid=os.getpid(),result=result))
        except BaseException as error:
            atomic(engineering/'failures'/(key+'.json'),dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
    expected=[engineering/(n['name']+'_device%02d'%d)/'PASS.json' for n in config['nodes'] for d in n['devices']]
    while not (engineering/'AGENT_ACCEPTANCE.json').exists():
        if next((engineering/'failures').glob('*.json'),None):return dict(status='MULTIDEVICE_REPLAY_FAILED_REQUIRES_REVIEW')
        if all(p.exists() for p in expected) and not (engineering/'ALL_DEVICES_READY.json').exists():
            atomic(engineering/'ALL_DEVICES_READY.json',dict(status='ALL_DEVICES_READY_REQUIRES_AGENT_REVIEW',time=stamp(),actual_devices=len(expected)))
        time.sleep(10)
    worker=dict(node=node['name'],device=device,pid=os.getpid(),hostname=socket.gethostname())
    live=stage/'workers'/(key+'_pid'+str(os.getpid())+'.json');cursor=0;completed=0
    try:
        while cursor<config['case_count']:
            offset=cursor;cursor+=config['chunk_size'];ident='R2_full_%06d'%offset
            receipt=stage/'receipts'/(ident+'.json')
            if receipt.exists():continue
            claim=stage/'claims'/ident;claim.parent.mkdir(parents=True,exist_ok=True)
            try:claim.mkdir()
            except FileExistsError:continue
            indices=list(range(offset,min(cursor,config['case_count'])))
            task=dict(config['task_template'],id=ident,indices=indices,output_stage=str(stage.relative_to(ROOT)))
            atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,task=task))
            atomic(live,dict(status='COMPUTING',time=stamp(),worker=worker,task=ident,completed=completed))
            result=evaluate(engine,task,pool)
            atomic(receipt,dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result));completed+=1
        atomic(live,dict(status='ALL_UNCLAIMED_REPLAY_CHUNKS_SERVED',time=stamp(),worker=worker,completed=completed))
        return dict(status='REPLAY_LEASE_EXHAUSTED',completed=completed)
    except BaseException as error:
        atomic(stage/'failures'/(ident+'.json'),dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc()));raise
