"""Additional CPU workers: cached queue cursor, unchanged scientific handlers.

Existing in-flight workers are retained. Rank count is configured at launch.
"""
from r2_common import *
import argparse
import importlib.util
import traceback


def main(args):
    setup('cpu_extra/'+args.worker,args.threads);compatibility()
    from threadpoolctl import threadpool_limits
    cached=[];version=None;cursor=0;modules={};started=time.monotonic()
    with threadpool_limits(args.threads):
        while not args.seconds or time.monotonic()-started<args.seconds:
            path=RUN/'tasks_cpu.json';current=path.stat().st_mtime_ns
            if version!=current:
                newer=read(path)
                if [t['id'] for t in newer[:len(cached)]]!=[t['id'] for t in cached]:cursor=0
                cached=newer;version=current
            task=None
            while cursor<len(cached):
                candidate=cached[cursor];cursor+=1
                if (RUN/'receipts_cpu'/(candidate['id']+'.json')).exists():continue
                folder=RUN/'claims_cpu'/candidate['id'];folder.parent.mkdir(parents=True,exist_ok=True)
                try:folder.mkdir()
                except FileExistsError:continue
                atomic(folder/'OWNER.json',dict(worker=args.worker,hostname=socket.gethostname(),pid=os.getpid(),time=stamp(),task=candidate))
                task=candidate;break
            status=RUN/'workers_cpu'/(args.worker+'.json')
            if task is None:
                atomic(status,dict(status='QUEUE_WAIT',time=stamp()));time.sleep(15);continue
            began=time.monotonic();atomic(status,dict(status='COMPUTING',time=stamp(),task=task['id']))
            try:
                source=ROOT/task['handler'];key=task['handler_sha256']
                assert source.resolve().is_relative_to(ROOT/'code') and sha(source)==key
                if key not in modules:
                    spec=importlib.util.spec_from_file_location('extra_cpu_'+key,source)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[key]=module
                value=modules[key].run(task)
                atomic(RUN/'receipts_cpu'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),worker=args.worker,task=task,seconds=time.monotonic()-began,result=value))
            except BaseException as error:
                atomic(RUN/'failures_cpu'/(task['id']+'.json'),dict(status='FAILED',time=stamp(),worker=args.worker,task=task,error=repr(error),traceback=traceback.format_exc()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',required=True);p.add_argument('--threads',type=int,default=2);p.add_argument('--seconds',type=int,default=0)
    main(p.parse_args())
