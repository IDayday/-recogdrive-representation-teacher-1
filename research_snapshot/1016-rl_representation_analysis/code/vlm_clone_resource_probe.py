"""Read-only CPU headroom and actual queue throughput; no experiment changes."""
from common import *
import argparse,psutil,socket,collections
from vlm_elastic_registry import DEST,BASE,configuration
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];lease=read(folder/'ADOPTED_CLONE.json')
    assert socket.gethostname().startswith(lease['job'])
    busy=[psutil.cpu_percent(interval=2) for _ in range(3)];cutoff=time.time()-300;ranks=set(c['gpu_ranks']);samples=[]
    for p in (BASE/'receipts').glob('*.json'):
        if p.stat().st_mtime<cutoff:continue
        r=read(p)
        if r['rank'] in ranks:samples.append(r)
    bystage=collections.defaultdict(list)
    for r in samples:bystage[r['task']['stage']].append(r)
    summaries={k:dict(tasks=len(v),records=sum(r['records'] for r in v),
        mean_task_seconds=sum(r['seconds'] for r in v)/len(v),
        sum_record_per_task_second=sum(r['records'] for r in v)/sum(r['seconds'] for r in v)) for k,v in bystage.items()}
    value=dict(status='PASS',time=stamp(),node=a.id,job=lease['job'],cpu_busy_samples=busy,
        cpu_affinity=len(os.sched_getaffinity(0)),available_memory=psutil.virtual_memory().available,
        recent_five_minute_actual_gpu_task_summaries=summaries,
        no_worker_count_or_model_or_scoring_change=True,source_sha256=sha(Path(__file__)))
    path=folder/'resource_probes'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json');atomic(path,value)
    atomic(folder/'RESOURCE_PROBE_LATEST.json',dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
    print('READ_ONLY_RESOURCE_PROBE',json.dumps(value),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);main(p.parse_args())
