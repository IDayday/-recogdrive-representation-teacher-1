"""Read-only CPU entitlement and task-process utilization observation."""
from r2_common import *
import argparse


def main(args):
    import psutil
    from collections import Counter
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node);assert node['job'] in socket.gethostname()
    known={}
    d=read(RUN/'nodes'/args.node/'LIVE.json')
    for k,v in d['children'].items():
        if '_cpu' in k:known[k]=v['pid']
    for folder in [RUN/'cpu_boost'/args.node,*list((RUN/'cpu_flex'/args.node).glob('*'))]:
        if not (folder/'LIVE.json').exists():continue
        for k,v in read(folder/'LIVE.json')['workers'].items():
            if v['returncode'] is None:known[k]=v['pid']
    processes={};before={}
    for name,pid in known.items():
        try:
            p=psutil.Process(pid);assert 'r2_cpu' in ' '.join(p.cmdline());processes[name]=p;t=p.cpu_times();before[name]=t.user+t.system
        except psutil.NoSuchProcess:continue
    started=time.monotonic();host_cpu=psutil.cpu_percent(interval=3);elapsed=time.monotonic()-started;usage={}
    for name,p in processes.items():
        try:
            t=p.cpu_times();usage[name]=dict(cpu_cores=(t.user+t.system-before[name])/elapsed,threads=p.num_threads(),status=p.status())
        except psutil.NoSuchProcess:continue
    cgroups={}
    for path in ['/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/cpu/cpu.cfs_quota_us','/sys/fs/cgroup/cpu/cpu.cfs_period_us','/sys/fs/cgroup/cpuset.cpus.effective']:
        try:cgroups[path]=Path(path).read_text().strip()
        except OSError:pass
    statuses=[]
    for p in (RUN/'workers_cpu').glob(args.node+'*.json'):
        statuses.append(read(p)['status'])
    result=dict(time=stamp(),node=args.node,host_cpu_percent=host_cpu,host_cpu_count=os.cpu_count(),affinity_count=len(os.sched_getaffinity(0)),
        cgroups=cgroups,owned_cpu_workers=len(usage),owned_cpu_cores=sum(v['cpu_cores'] for v in usage.values()),worker_processes=usage,queue_worker_status_counts=dict(Counter(statuses)),
        interpretation='Host CPU% may use a larger denominator than the job entitlement; do not chase it blindly.')
    path=ROOT/'provenance/cpu_observation'/args.node/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json');atomic(path,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['worker_processes']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
