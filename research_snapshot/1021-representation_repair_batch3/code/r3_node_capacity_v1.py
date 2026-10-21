"""Read-only capacity after task-owned model-lane expansion."""
from r3_common import *
import argparse
import socket


def main(a):
    setup('capacity/'+a.node,threads=1)
    import psutil
    import torch
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    cards=[]
    for device in node['devices']:
        free,total=torch.cuda.mem_get_info(device);cards.append(dict(device=device,name=torch.cuda.get_device_name(device),free_bytes=free,total_bytes=total))
    result=dict(status='PASS_READ_ONLY_NODE_CAPACITY',time=stamp(),node=a.node,job=node['job'],devices=cards,
        minimum_free_gpu_bytes=min(c['free_bytes'] for c in cards),CPU_percent=psutil.cpu_percent(interval=1),
        memory_available=psutil.virtual_memory().available,cpu_affinity=len(os.sched_getaffinity(0)),
        no_model_or_scientific_configuration_changed=True,no_process_signals=True)
    path=ROOT/a.output;assert not path.exists();atomic(path,result)
    print(json.dumps({k:v for k,v in result.items() if k!='devices'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--output',required=True);main(p.parse_args())
