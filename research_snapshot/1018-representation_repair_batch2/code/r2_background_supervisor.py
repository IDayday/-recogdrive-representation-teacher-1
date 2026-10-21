"""Retained, configurable supplementary GPU lanes; primary workers stay active."""
from r2_common import *
import argparse
import subprocess


def main(args):
    setup('background_supervisor/'+args.node)
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname()
    devices=[int(x) for x in args.devices.split(',')];assert set(devices)<=set(node['devices'])
    folder=RUN/'background_supervisor'/args.node/args.tag;folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'START.json').exists()
    script=ROOT/'code/r2_gpu_background.py';processes={};streams=[]
    atomic(folder/'START.json',dict(time=stamp(),pid=os.getpid(),job=node['job'],devices=devices,script_sha256=sha(script),primary_workers_retained=True))
    for device in devices:
        stream=(folder/(str(device)+'.log')).open('a');streams.append(stream)
        processes[str(device)]=subprocess.Popen([sys.executable,'-u','-B',str(script),'--node',args.node,'--device',str(device),
            '--tag',args.tag,'--seconds','0'],cwd=ROOT,env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(device)),stdout=stream,stderr=subprocess.STDOUT)
    while True:
        states={name:dict(pid=p.pid,returncode=p.poll()) for name,p in processes.items()}
        for name,state in states.items():
            if state['returncode'] not in [None,0]:
                path=RUN/'failures'/('background_supervisor_'+args.node+'_'+name+'.json')
                if not path.exists():atomic(path,dict(status='FAILED',time=stamp(),node=args.node,device=int(name),process=state,log=str((folder/(name+'.log')).relative_to(ROOT))))
        atomic(folder/'LIVE.json',dict(time=stamp(),node=args.node,devices=devices,processes=states,primary_workers_retained=True))
        time.sleep(15)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--devices',default='0,4,8,12');p.add_argument('--tag',default='retained_overlap_v1');main(p.parse_args())
