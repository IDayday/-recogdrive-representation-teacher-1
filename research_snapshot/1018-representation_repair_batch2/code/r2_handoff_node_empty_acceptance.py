"""Actual PPU/process/keeper/receiver verification after B1 compute retirement.

Does not activate the owner or publish the final cloud-backed acceptance gate.
"""
from r2_common import *
import psutil

DEST=ROOT/'resources/handoffs/peer_b1_20261019'


def task_processes():
    found=[]
    for p in psutil.process_iter(['pid','create_time','cmdline','cwd','status']):
        try:
            d=p.info
            if d['status']==psutil.STATUS_ZOMBIE:continue
            scripts=[]
            for token in d['cmdline'] or []:
                if not token.endswith(('.py','.sh')):continue
                path=Path(token)
                if not path.is_absolute():path=Path(d['cwd'] or '/')/path
                path=path.resolve()
                if path.is_relative_to(ROOT) or path.is_relative_to(OLD):scripts.append(str(path))
            if scripts:found.append(dict(d,scripts=scripts,children=[c.pid for c in p.children(recursive=True)]))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return found


def main():
    setup('handoff_node_empty_acceptance');assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert read(DEST/'COMPUTE_STOPPED_AWAITING_ACCEPTANCE.json')['no_claim_deleted']
    lease=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']=='peer_b1')
    assert not lease['active_for_batch2'] and not lease['devices']
    receiver=DEST/'colleague_launcher';assert not(receiver/'OWNER_ACTIVATION.json').exists()
    startup=read(DEST/'launcher_engineering/PASS.json')
    assert startup['source_sha256']==sha(ROOT/'code/r2_colleague_inbox_launcher.py')
    keeper_path=OLD/'vlm_repair_v1/elastic_v1/nodes/elastic_004/attestations/dlcqdtslnqnytsc7/LIVE.json'
    import torch
    assert torch.cuda.is_available() and torch.cuda.device_count()==16
    observations=[]
    for iteration in range(2):
        keeper=read(keeper_path);assert keeper['pid']==5 and keeper['status']=='CORE_EXITED_CONTAINER_RETAINED'
        assert keeper['job']=='dlcqdtslnqnytsc7' and keeper['main_retained']
        assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(keeper['time'])).total_seconds()<90
        live=read(receiver/'LIVE.json');assert live['job']=='dlcqdtslnqnytsc7' and live['status']=='WAITING_OWNER_ACTIVATION'
        assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()<90
        processes=task_processes();allowed={5,live['pid'],os.getpid()}
        assert {p['pid'] for p in processes}==allowed,[(p['pid'],p['scripts']) for p in processes]
        assert not psutil.Process(live['pid']).children(recursive=True)
        devices=[]
        for i in range(16):
            free,total=torch.cuda.mem_get_info(i)
            assert free/total>.95,(i,free,total)
            devices.append(dict(device=i,name=torch.cuda.get_device_name(i),free_bytes=free,total_bytes=total,free_fraction=free/total))
        observations.append(dict(time=stamp(),processes=processes,keeper=keeper,receiver=live,devices=devices,
            cpu_affinity=len(os.sched_getaffinity(0)),memory_available=psutil.virtual_memory().available))
        if iteration==0:time.sleep(3)
    atomic(DEST/'NODE_EMPTY_HARDWARE_AND_PROCESS_ACCEPTANCE.json',dict(status='PASS_REAL_NODE_EMPTY_FOR_COLLEAGUE',
        time=stamp(),job='dlcqdtslnqnytsc7',observations=observations,own_compute_processes=0,
        original_DLC_keeper_retained=True,independent_receiver_idle=True,all16_actual_devices_over95percent_memory_free=True,
        final_cloud_running_and_clock_check_still_required=True,no_owner_activation_or_cloud_action=True))
    print(json.dumps(dict(status='PASS_REAL_NODE_EMPTY_FOR_COLLEAGUE',devices=16,own_compute=0,keeper=5,
        receiver=observations[-1]['receiver']['pid'],minimum_memory_free_fraction=min(d['free_fraction'] for d in observations[-1]['devices']))))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(DEST/'EMPTY_ACCEPTANCE_FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc(),
            no_automatic_resource_change=True))
        raise
