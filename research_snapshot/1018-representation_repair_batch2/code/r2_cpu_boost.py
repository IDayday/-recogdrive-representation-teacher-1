"""Launch only task-owned supplemental CPU workers, retaining original workers."""
from r2_common import *
import argparse
import subprocess
import psutil


def main(args):
    setup('cpu_boost/'+args.node)
    config=read(ROOT/'resources/NODES.json');node=next(n for n in config['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname(),(node['job'],socket.gethostname())
    folder=RUN/'cpu_boost'/args.node;folder.mkdir(parents=True,exist_ok=True)
    identity=folder/'START.json';assert not identity.exists(),'Do not launch duplicate worker set'
    script=ROOT/'code/r2_cpu_extra.py';streams=[];processes={}
    atomic(identity,dict(time=stamp(),pid=os.getpid(),job=node['job'],count=args.count,threads=args.threads,source_sha256=sha(script)))
    for j in range(args.count):
        worker=args.node+'_extra%02d'%j;stream=(folder/(worker+'.log')).open('a');streams.append(stream)
        processes[worker]=subprocess.Popen([sys.executable,'-u','-B',str(script),'--worker',worker,'--threads',str(args.threads)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    while True:
        states={name:dict(pid=p.pid,returncode=p.poll()) for name,p in processes.items()}
        atomic(folder/'LIVE.json',dict(time=stamp(),cpu=psutil.cpu_percent(),memory_available=psutil.virtual_memory().available,workers=states))
        time.sleep(30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--count',type=int,default=24)
    p.add_argument('--threads',type=int,default=2);main(p.parse_args())
