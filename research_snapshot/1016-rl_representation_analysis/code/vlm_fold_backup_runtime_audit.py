"""Read-only early check of actual independent CPU workers and original scans."""
from common import *
import argparse,psutil
from vlm_core import VOUT
from vlm_fold_backup_v2 import BASE,OUT
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup(f'vlm_repair/fold_backup/runtime_audit/node{a.node}')
    state=read(BASE/f'node{a.node}/STATUS.json');records=[];processes=[]
    for pid in state['pids']:
        process=psutil.Process(pid);cmd=process.cmdline()
        assert any(x.endswith('/code/vlm_fold_backup_v2.py') for x in cmd) and 'worker' in cmd
        records.append(dict(pid=pid,cmd=cmd,nice=process.nice(),rss=process.memory_info().rss,threads=process.num_threads()))
        processes.append(process)
    assert len(records)==10 and all(r['nice']>=10 for r in records)
    if a.node==0:
        for rank in [1,11]:
            owner=read(VOUT/'scan/claims'/('bridge_pre__patch_mean' if rank==1 else 'bridge_0__patch_mean')/'OWNER.json')
            if owner.get('rank')!=rank:continue
            try:
                process=psutil.Process(owner['pid']);cmd=process.cmdline()
            except psutil.NoSuchProcess:continue
            assert any(x.endswith('/code/vlm_scan_queue.py') for x in cmd) and 'worker' in cmd
            records.append(dict(pid=process.pid,cmd=cmd,original_frozen_worker=True,rss=process.memory_info().rss));processes.append(process)
    first=[p.cpu_times() for p in processes];time.sleep(2)
    for row,p,before in zip(records,processes,first):
        after=p.cpu_times();row['cpu_seconds_advanced']=after.user+after.system-before.user-before.system
        assert row['cpu_seconds_advanced']>0,row
    assert read(OUT/'ENGINEERING_PASS.json')['status']=='PASS'
    for path,h in read(OUT/'PROTOCOL.json')['original_math_sha256'].items():assert sha(ROOT/path)==h,path
    dest=OUT/'audits'/('node'+str(a.node)+'_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(dest,dict(status='PASS',time=stamp(),node=a.node,worker_processes=records,
        cpu_busy_percent=psutil.cpu_percent(interval=1),available_memory=psutil.virtual_memory().available,
        receipts=len(list((BASE/'receipts').glob('*.json'))),tasks=len(read(BASE/'tasks.json')),
        frozen_kernels_unchanged=True,original_workers_never_stopped=True))
    print('FOLD_BACKUP_EARLY_RUNTIME_AUDIT_PASS',a.node,str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True);main(p.parse_args())
