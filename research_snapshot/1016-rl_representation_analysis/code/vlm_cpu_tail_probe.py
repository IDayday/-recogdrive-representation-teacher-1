"""Read-only identities and CPU progress for this task's remaining producers."""
from common import *
import argparse,psutil,socket
from vlm_elastic_registry import DEST
from repair_queue_v2 import atomic_unique as atomic

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);p.add_argument('--output',required=True);a=p.parse_args()
    n=next(x for x in read(DEST/'REGISTRY.json')['nodes'] if x['id']==f'legacy_{a.node}')
    assert socket.gethostname().startswith(n['job'])
    scan=DEST.parent/'scan';done={p.stem for p in (scan/'receipts').glob('*.json')};processes=[];tail=[]
    for proc in psutil.process_iter(['pid','cwd','cmdline']):
        try:
            if proc.info['cwd']!=str(ROOT):continue
            cmd=proc.info['cmdline'] or [];names=[Path(s).name for s in cmd if str(s).endswith('.py')]
            if not any(s.startswith('vlm_') for s in names):continue
            times=proc.cpu_times();processes.append(dict(pid=proc.pid,created=proc.create_time(),cmdline=cmd,cpu_seconds=times.user+times.system,threads=proc.num_threads(),status=proc.status(),nice=proc.nice()))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    own={x['pid']:x for x in processes}
    for folder in (scan/'claims').iterdir():
        if folder.name in done or not (folder/'OWNER.json').exists():continue
        owner=read(folder/'OWNER.json');pid=owner['pid']
        if pid in own and any(Path(s).name in ['vlm_scan_queue.py','vlm_scan_wave.py','vlm_scan_wave_v2.py','vlm_scan_spare.py','vlm_scan_owner_recovery.py'] for s in own[pid]['cmdline']):
            tail.append(dict(task=folder.name,owner=owner,process=own[pid]))
    result=dict(status='PASS',time=stamp(),job=n['job'],node=a.node,host_cpu_percent=psutil.cpu_percent(interval=1),
        available_memory=psutil.virtual_memory().available,completed_scan_cells=len(done),remaining_owned_scan=tail,owned_processes=processes,no_process_or_output_changed=True)
    atomic(ROOT/a.output,result);print(json.dumps(dict(status='PASS',path=a.output,remaining_owned=len(tail),owned_processes=len(processes),cpu_percent=result['host_cpu_percent'])),flush=True)
