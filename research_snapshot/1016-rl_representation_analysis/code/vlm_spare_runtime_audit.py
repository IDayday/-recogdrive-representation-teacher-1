"""Early actual-process and committed-output check for the spare CPU wave."""
from common import *
import argparse,psutil
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup(f'vlm_repair/scan_spare/audit/node{a.node}')
    folder=VOUT/f'scan_spare/node{a.node}';state=read(folder/'STATUS.json');smoke=read(folder/'SMOKE_PASS.json');assert smoke['status']=='PASS'
    processes=[];records=[]
    for rank,pid in state['workers'].items():
        p=psutil.Process(pid);command=p.cmdline();assert any(s.endswith('/code/vlm_scan_spare.py') for s in command) and 'worker' in command
        assert p.nice()>=10 and p.status()!=psutil.STATUS_ZOMBIE
        processes.append(p);records.append(dict(rank=int(rank),pid=pid,rss=p.memory_info().rss,nice=p.nice(),cpu_before=p.cpu_times().user+p.cpu_times().system))
    assert len(records)==16;time.sleep(2)
    for row,p in zip(records,processes):
        value=p.cpu_times();row['cpu_seconds_advanced']=value.user+value.system-row.pop('cpu_before')
    for path,h in read(VOUT/'SPARE_SCAN_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    ranks={r['rank'] for r in records};committed=[]
    for p in (VOUT/'scan/receipts').glob('*.json'):
        receipt=read(p)
        if receipt['rank'] not in ranks:continue
        rp=VOUT/'scan/results'/p.name;assert sha(rp)==receipt['result_sha256'];result=read(rp);proof=read(VOUT/'cells'/p.name)
        assert result['source_sha256']==proof['sha256']
        if result['status']=='COMPLETE':assert result['configs']==11633 and result['training_class_sizes']==[74900,1850]
        committed.append(dict(task=receipt['task']['id'],status=result['status'],source_sha256=proof['sha256']))
    dest=VOUT/'scan_spare/audits'/('node'+str(a.node)+'_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(dest,dict(status='PASS',time=stamp(),node=a.node,worker_processes=records,committed=committed,
        cpu_busy_percent=psutil.cpu_percent(interval=1),available_memory=psutil.virtual_memory().available,
        numeric_smoke_all_16_pass=True,source_model_and_math_unchanged=True,no_old_process_stopped=True))
    print('SPARE_SCAN_EARLY_ACTUAL_AUDIT_PASS',a.node,len(committed),str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True);main(p.parse_args())
