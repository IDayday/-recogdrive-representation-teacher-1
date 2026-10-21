"""One node-local smoke coordinator; configurable physical card list."""
from d4_common import *
import argparse
import socket
import subprocess


def main(a):
    assigned=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(assigned['job']+'-')
    node=next(n for n in read(B3/'resources/REGISTRY.json')['nodes'] if n['name']==a.node)
    devices=node['devices'];assert len(devices)==len(set(devices)) and devices
    folder=ROOT/'runs/ddp_smoke_v1'/a.node;marker=folder/'LAUNCH.json';assert not marker.exists()
    # Reserving a private localhost rendezvous port changes no global service.
    with socket.socket() as port:port.bind(('127.0.0.1',0));master_port=port.getsockname()[1]
    children=[]
    for rank,device in enumerate(devices):
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(device),MASTER_ADDR='127.0.0.1',MASTER_PORT=str(master_port),RANK=str(rank),WORLD_SIZE=str(len(devices)),LOCAL_RANK='0')
        command=[sys.executable,'-u','-B',str(ROOT/'code/d4_ddp_smoke_v1.py'),'--rank',str(rank),'--world-size',str(len(devices)),'--node',a.node,'--group',assigned['group']]
        log=folder/('rank%02d.log'%rank);log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('x') as output:child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        children.append(dict(rank=rank,device=device,pid=child.pid,command=command))
    atomic(marker,dict(status='LAUNCHED_NOT_ACCEPTED',time=stamp(),node=a.node,group=assigned['group'],devices=devices,master_port=master_port,children=children))
    print(json.dumps(dict(status='LAUNCHED',node=a.node,group=assigned['group'],actual_devices=len(devices))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
