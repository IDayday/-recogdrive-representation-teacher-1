"""Launch one assigned H/T/HT program on configurable verified local devices."""
from d4_common import *
import argparse
import socket
import subprocess


def main(a):
    config_path=Path(a.config).resolve();assert config_path.is_relative_to(ROOT/'configs');config=read(config_path)
    assert socket.gethostname().startswith(config['job']+'-')
    assert (ROOT/'runs/full_context_replay_v1/AGENT_ACCEPTANCE.json').exists()
    assert (ROOT/'provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V2.json').exists()
    for name,hashed in config['code_hashes'].items():assert sha(ROOT/'code'/name)==hashed
    if not config['engineering_only']:assert (ROOT/'provenance/TRAINING_PROGRAM_ENGINEERING_ACCEPTANCE_V2.json').exists()
    folder=ROOT/'runs'/config['run_id'];marker=folder/('RESUME_LAUNCH.json' if a.resume else 'LAUNCH.json');assert not marker.exists()
    with socket.socket() as port:port.bind(('127.0.0.1',0));master_port=port.getsockname()[1]
    children=[]
    for rank,device in enumerate(config['devices']):
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(device),MASTER_ADDR='127.0.0.1',MASTER_PORT=str(master_port),RANK=str(rank),WORLD_SIZE=str(config['world_size']),LOCAL_RANK='0')
        command=[sys.executable,'-u','-B',str(ROOT/'code'/config['training_entrypoint']),'--config',str(config_path),'--run',config['run_id'],'--rank',str(rank),'--world-size',str(config['world_size'])]
        if a.resume:command.extend(['--resume',a.resume])
        if a.stop_after_epoch:command.extend(['--stop-after-epoch',str(a.stop_after_epoch)])
        log=folder/'logs'/(('rank%02d_resume.log' if a.resume else 'rank%02d.log')%rank);log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('x') as output:child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        children.append(dict(rank=rank,device=device,pid=child.pid,command=command))
    atomic(marker,dict(status='LAUNCHED_NOT_YET_ACCEPTED',time=stamp(),configuration_sha256=sha(config_path),run=config['run_id'],node=config['node'],
        group=config['group'],devices=config['devices'],master_port=master_port,children=children))
    print(json.dumps(dict(status='LAUNCHED',run=config['run_id'],group=config['group'],actual_devices=len(children))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--resume');p.add_argument('--stop-after-epoch',type=int,default=0);main(p.parse_args())
