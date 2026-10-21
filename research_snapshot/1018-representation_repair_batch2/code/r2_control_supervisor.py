"""DLC-resident controller supervisor: preserve failures, never release nodes."""
from r2_common import *
import argparse
import subprocess
import psutil


def main(args):
    setup('control_plane/'+args.node)
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname()
    folder=RUN/'control_plane';folder.mkdir(parents=True,exist_ok=True)
    guard=(folder/'LEADER.lock').open('a+');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config_path=ROOT/'config/CONTROL_SCRIPTS_V1.json';config=read(config_path)
    atomic(folder/'READY.json',dict(time=stamp(),node=args.node,job=node['job'],pid=os.getpid(),
           hostname=socket.gethostname(),config_sha256=sha(config_path),physical_cpus=psutil.cpu_count(),
           memory_available=psutil.virtual_memory().available,has_cloud_credentials_uri=bool(os.environ.get('ALIBABA_CLOUD_CREDENTIALS_URI')),
           will_wait_for_handoff=True,retained=True))
    while not (folder/'HANDOFF_RELEASE.json').exists():time.sleep(2)
    processes={};streams=[]
    while True:
        for child in read(config_path)['scripts']:
            name=child['id']
            if name in processes:continue
            path=ROOT/child['script'];assert sha(path)==child['source_sha256']
            log=folder/'logs'/(name+'.log');log.parent.mkdir(parents=True,exist_ok=True)
            stream=log.open('a');streams.append(stream)
            processes[name]=subprocess.Popen([sys.executable,'-u','-B',str(path),*child.get('arguments',[])],
                     cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        states={name:dict(pid=p.pid,returncode=p.poll()) for name,p in processes.items()}
        for name,state in states.items():
            if state['returncode'] not in [None,0]:
                failure=RUN/'failures'/('control_'+name+'.json')
                if not failure.exists():atomic(failure,dict(status='FAILED',time=stamp(),node=args.node,job=node['job'],
                     controller=name,process=state,log=str((folder/'logs'/(name+'.log')).relative_to(ROOT)),
                     action='No automatic restart or resource release; preserve source and await agent review.'))
        atomic(folder/'LIVE.json',dict(time=stamp(),node=args.node,job=node['job'],pid=os.getpid(),children=states,
               failures={k:v for k,v in states.items() if v['returncode'] not in [None,0]},retained=True))
        time.sleep(15)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);args=p.parse_args()
    try:main(args)
    except BaseException as error:
        import traceback
        atomic(RUN/'failures/control_supervisor.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
