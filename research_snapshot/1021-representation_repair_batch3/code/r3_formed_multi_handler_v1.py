"""One engineering execution per actual device using retained loaded models.

Sibling lanes wait for the finite device checklist, preventing early lanes from
consuming all service slots before slower devices reach the engineering stage.
No model launch, cloud operation or scientific candidate admission occurs here.
"""
from r3_common import *
import socket
import traceback


def run(engine,task,pool):
    from r3_formed_integration_v1 import run as integration
    stage=ROOT/task['stage'];config=read(stage/'DEVICE_CHECKLIST.json')
    assert sha(stage/'DEVICE_CHECKLIST.json')==task['checklist_sha256']
    node=next(n for n in config['nodes'] if socket.gethostname().startswith(n['job']+'-'))
    device=int(os.environ['CUDA_VISIBLE_DEVICES']);assert device in node['devices']
    claim=stage/'device_claims'/(node['name']+'_device%02d'%device);claim.parent.mkdir(parents=True,exist_ok=True)
    owner=False
    try:claim.mkdir();owner=True
    except FileExistsError:pass
    target=ROOT/'runs/formed_integration_v1/multi_v1'/node['name']/('device%02d'%device)/'PASS.json'
    if owner:
        atomic(claim/'OWNER.json',dict(time=stamp(),hostname=socket.gethostname(),pid=os.getpid(),device=device))
        try:integration(engine,dict(name='multi_v1',node=node['name']),pool)
        except BaseException as error:
            atomic(stage/'failures'/(node['name']+'_device%02d'%device+'.json'),dict(status='FAILED',time=stamp(),hostname=socket.gethostname(),pid=os.getpid(),error=repr(error),traceback=traceback.format_exc()))
            raise
    began=time.monotonic()
    expected=[ROOT/'runs/formed_integration_v1/multi_v1'/n['name']/('device%02d'%d)/'PASS.json' for n in config['nodes'] for d in n['devices']]
    while True:
        failed=list((stage/'failures').glob('*.json'))
        if failed:return dict(status='ENGINEERING_FAILED_REQUIRES_REVIEW',failure=str(failed[0].relative_to(ROOT)),no_formal_expansion=True)
        if all(p.exists() for p in expected):
            return dict(status='ALL_ACTUAL_DEVICES_READY_REQUIRES_AGENT_ADMISSION',device_proof=str(target.relative_to(ROOT)),owner=owner,devices=len(expected))
        if time.monotonic()-began>1800:
            atomic(stage/'failures'/('wait_timeout_'+str(os.getpid())+'.json'),dict(status='WAIT_TIMEOUT_REQUIRES_REVIEW',time=stamp(),hostname=socket.gethostname(),pid=os.getpid()))
            return dict(status='ENGINEERING_WAIT_TIMEOUT_NO_FORMAL_EXPANSION')
        time.sleep(10)
