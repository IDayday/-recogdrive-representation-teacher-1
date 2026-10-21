"""Verify idle B1 and retire only its idle colleague receiver for authorized reuse."""
from r2_common import *
import psutil

DEST=ROOT/'resources/rejoins/peer_b1_20261019T0540'
HANDOFF=ROOT/'resources/handoffs/peer_b1_20261019'


def main():
    setup('peer_b1_rejoin_prepare_v2')
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert read(DEST/'INTENT.json')['five_hours_is_estimate_not_automatic_stop']
    assert not (DEST/'PREPARED.json').exists()
    box=HANDOFF/'colleague_launcher'
    assert not (box/'OWNER_ACTIVATION.json').exists()
    assert not list((box/'pending').glob('*.json'))
    assert not list((box/'receipts').glob('*.json'))
    live=read(box/'LIVE.json');accepted=read(HANDOFF/'ACCEPTED_EMPTY_FOR_OWNER.json')
    assert live['status']=='WAITING_OWNER_ACTIVATION' and live['pid']==accepted['independent_receiver_PID']
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()<90
    receiver=psutil.Process(live['pid'])
    expected=[str(ROOT/'code/r2_colleague_inbox_launcher.py')]
    assert all(s in receiver.cmdline() for s in expected)
    historical=read(HANDOFF/'NODE_EMPTY_HARDWARE_AND_PROCESS_ACCEPTANCE.json')
    prior=next(p for p in historical['observations'][-1]['processes'] if p['pid']==receiver.pid)
    assert receiver.create_time()==prior['create_time']
    assert Path(receiver.cwd()).resolve()==Path(prior['cwd']).resolve()
    assert receiver.uids().real==os.getuid() and not receiver.children(recursive=True)
    from r2_handoff_node_empty_acceptance import task_processes
    processes=task_processes()
    assert {p['pid'] for p in processes}=={5,receiver.pid,os.getpid()},processes
    import torch
    assert torch.cuda.is_available() and torch.cuda.device_count()==16
    devices=[]
    for i in range(16):
        free,total=torch.cuda.mem_get_info(i);assert free/total>.95
        devices.append(dict(device=i,name=torch.cuda.get_device_name(i),free_bytes=free,total_bytes=total))
    assert len(os.sched_getaffinity(0))>=128 and psutil.virtual_memory().available>256*1024**3
    owner=dict(pid=receiver.pid,created=receiver.create_time(),cmdline=receiver.cmdline(),uid=receiver.uids().real)
    atomic(DEST/'BEFORE_RECEIVER_RETIRE.json',dict(time=stamp(),process=owner,processes=processes,devices=devices,
        cpu_affinity=len(os.sched_getaffinity(0)),memory_available=psutil.virtual_memory().available,
        receiver_has_no_owner_activation_or_work=True))
    # Identity is checked immediately before the only signal. No other process is stopped.
    assert receiver.create_time()==owner['created'] and receiver.cmdline()==owner['cmdline']
    receiver.terminate()
    try:receiver.wait(timeout=15)
    except psutil.TimeoutExpired:raise RuntimeError('Idle receiver did not exit; do not force kill or launch research.')
    assert psutil.Process(5).is_running()
    atomic(DEST/'PREPARED.json',dict(status='PASS_IDLE_NODE_RECLAIMED_FOR_RESEARCH',time=stamp(),job='dlcqdtslnqnytsc7',
        retired_only_idle_receiver=owner,keeper_PID5_retained=True,previous_handoff_materials_preserved=True,
        no_cloud_stop_or_release=True,no_scientific_task_stopped=True))
    atomic(box/'RECEIVER_SUSPENDED_BY_USER.json',dict(time=stamp(),reason='User authorized research reuse pending later handoff.',
        proof=str((DEST/'PREPARED.json').relative_to(ROOT)),activation_and_tasks_absent=True,restart_on_next_handoff_only=True))
    print(json.dumps(dict(status='PASS_IDLE_NODE_RECLAIMED_FOR_RESEARCH',devices=16,keeper=5)))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(DEST/'PREPARE_V2_FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
