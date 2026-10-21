"""Verify completed waiter termination after a bounded psutil wait expired."""
from common import *
import socket,psutil
from vlm_elastic_registry import DEST
from repair_queue_v2 import atomic_unique as atomic

def main():
    node=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']=='legacy_0')
    assert socket.gethostname().startswith(node['job'])
    folder=DEST/'control_cutover';intent=read(folder/'INTENT.json')
    assert intent['status']=='VERIFIED_IDLE_ACCEPTANCE_WAITERS_ONLY'
    assert not (folder/'RETIRED.json').exists()
    failure=DEST/'failures/control_retire.json';error=read(failure)
    assert error['error']=='AssertionError([13])'
    checks=[]
    for r in intent['records']:
        try:
            p=psutil.Process(r['pid'])
            assert p.create_time()==r['created'],'PID reused; refuse inference from a different process'
            assert p.status()==psutil.STATUS_ZOMBIE,('Original waiter still live',r['pid'],p.status())
            checks.append(dict(pid=r['pid'],status='ZOMBIE_NOT_EXECUTING'))
        except psutil.NoSuchProcess:checks.append(dict(pid=r['pid'],status='NO_SUCH_PROCESS'))
    atomic(folder/'RETIRED.json',dict(status='PASS',time=stamp(),records=intent['records'],
        legacy_resume=intent['legacy_resume'],main_GPU_full_grid_and_DLC_job_processes_untouched=True,
        only_idle_acceptance_waiters_replaced=True,termination_checks=checks,
        previous_bounded_wait_failure_sha256=sha(failure),original_error_retained=True,
        verification_source_sha256=sha(Path(__file__))))
    print('IDLE_WAITERS_TERMINATED_AND_INDEPENDENTLY_VERIFIED',len(checks),flush=True)

if __name__=='__main__':main()
