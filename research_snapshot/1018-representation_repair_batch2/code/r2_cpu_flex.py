"""Task-boundary bounded CPU concurrency trial; primary processes are retained."""
from r2_common import *
import argparse
import subprocess


def main(args):
    setup('cpu_flex/'+args.node+'/'+args.tag)
    import psutil
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node)
    assert node['job'] in socket.gethostname()
    assert psutil.virtual_memory().available>256*1024**3
    folder=RUN/'cpu_flex'/args.node/args.tag;folder.mkdir(parents=True,exist_ok=True);assert not (folder/'START.json').exists()
    began=time.monotonic();processes={};streams=[]
    atomic(folder/'START.json',dict(time=stamp(),pid=os.getpid(),count=args.count,threads=args.threads,seconds=args.seconds,node=args.node,primary_processes_unchanged=True))
    for j in range(args.count):
        name=args.node+'_flex_'+args.tag+'_%02d'%j;stream=(folder/(name+'.log')).open('a');streams.append(stream)
        processes[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/r2_cpu_flex_worker.py'),'--worker',name,'--threads',str(args.threads),'--seconds',str(args.seconds)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    while True:
        states={name:dict(pid=p.pid,returncode=p.poll()) for name,p in processes.items()}
        atomic(folder/'LIVE.json',dict(time=stamp(),workers=states,cpu_percent=psutil.cpu_percent(),memory_available=psutil.virtual_memory().available,seconds=time.monotonic()-began))
        if any(v['returncode'] not in [None,0] for v in states.values()):
            path=RUN/'failures'/('cpu_flex_'+args.node+'_'+args.tag+'.json')
            if not path.exists():atomic(path,dict(time=stamp(),states=states,status='CHILD_FAILURE_RETAINED'))
        if all(v['returncode'] is not None for v in states.values()):
            atomic(folder/'COMPLETE.json',dict(time=stamp(),seconds=time.monotonic()-began,states=states,node_released=False,primary_processes_stopped=False));return
        time.sleep(30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--tag',required=True);p.add_argument('--count',type=int,default=16);p.add_argument('--threads',type=int,default=2);p.add_argument('--seconds',type=int,default=600)
    main(p.parse_args())
