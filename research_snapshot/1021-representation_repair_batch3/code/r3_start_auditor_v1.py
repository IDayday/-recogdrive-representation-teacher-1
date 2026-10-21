"""Start a private CPU auditor once on a verified retained node; no restarts."""
from r3_common import *
import argparse
import socket
import subprocess


def main(a):
    registry=read(ROOT/'resources/REGISTRY.json');node=next(v for v in registry['nodes'] if v['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    stage=ROOT/'runs'/a.stage;assert (stage/'producer.json').exists();marker=stage/'audit_v1/launches'/(a.node+'.json')
    if marker.exists():
        previous=read(marker)
        try:
            command=(Path('/proc')/str(previous['pid'])/'cmdline').read_bytes().split(b'\0')
            assert str(ROOT/'code/r3_incremental_audit_v1.py').encode() in command
            print(json.dumps(dict(status='ALREADY_RUNNING',pid=previous['pid'],node=a.node)),flush=True);return
        except FileNotFoundError:raise RuntimeError('Previous auditor exited; review evidence before any new version')
    log=stage/'audit_v1/logs'/(a.node+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-u','-B',str(ROOT/'code/r3_incremental_audit_v1.py'),'--stage',a.stage,'--node',a.node,'--workers',str(a.workers)]
    with log.open('x') as output:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    proof=dict(status='STARTED_NOT_ACCEPTED',time=stamp(),pid=process.pid,node=a.node,hostname=socket.gethostname(),command=command,workers=a.workers,log=str(log.relative_to(ROOT)),source_sha256=sha(ROOT/'code/r3_incremental_audit_v1.py'))
    atomic(marker,proof);print(json.dumps({k:proof[k] for k in ['status','node','pid','workers']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=2);main(p.parse_args())
