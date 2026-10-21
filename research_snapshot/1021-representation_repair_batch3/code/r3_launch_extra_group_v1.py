"""Configurable extra lanes, individually gold-verified before claiming work."""
from r3_common import *
import argparse
import socket
import subprocess


def main(a):
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node);assert socket.gethostname().startswith(node['job']+'-')
    group=read(ROOT/a.group);selected=[w for w in group['workers'] if w['node']==a.node];output=[]
    for setting in selected:
        device=setting['device'];lane=setting['lane'];assert device in node['devices']
        worker=a.node+'_device%02d_lane%d'%(device,lane);dest=ROOT/'runs/extra_engineering_v1'/worker;marker=dest/'LAUNCH.json'
        command=[sys.executable,'-u','-B',str(ROOT/'code/r3_extra_worker_v1.py'),'--node',a.node,'--device',str(device),'--lane',str(lane)]
        if marker.exists():
            previous=read(marker);args=(Path('/proc')/str(previous['pid'])/'cmdline').read_bytes().split(b'\0')
            assert [v.decode() for v in args if v]==previous['command'];output.append(dict(worker=worker,status='EXISTING_VERIFIED',pid=previous['pid']));continue
        dest.mkdir(parents=True,exist_ok=True);env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(device),PYTHONDONTWRITEBYTECODE='1')
        with (dest/'stdout.log').open('x') as log:process=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        atomic(marker,dict(time=stamp(),pid=process.pid,node=a.node,device=device,lane=lane,command=command,physical_card_count_unchanged=True,group=a.group))
        output.append(dict(worker=worker,status='STARTED_PENDING_GOLDEN',pid=process.pid));time.sleep(.5)
    atomic(ROOT/'resources/nodes'/a.node/'EXTRA_GROUP_LAUNCH.json',dict(time=stamp(),group=a.group,workers=output))
    print(json.dumps(dict(node=a.node,started=sum(v['status']=='STARTED_PENDING_GOLDEN' for v in output),already_verified=sum(v['status']=='EXISTING_VERIFIED' for v in output))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--group',required=True);main(p.parse_args())
