"""Start CPU-only elastic auditors once, without replacing another process."""
from r3_common import *
import argparse
import socket
import subprocess


def main(a):
    node=next(v for v in read(ROOT/'resources/REGISTRY.json')['nodes'] if v['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    marker=ROOT/'runs/elastic_audit_launches'/(a.node+'.json')
    script=ROOT/'code/r3_stage_auditor_v1.py'
    if marker.exists():
        old=read(marker);command=(Path('/proc')/str(old['pid'])/'cmdline').read_bytes().split(b'\0')
        assert str(script).encode() in command
        print(json.dumps(dict(status='ALREADY_RUNNING',pid=old['pid'],node=a.node)));return
    log=ROOT/'runs/elastic_audit_logs'/(a.node+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-u','-B',str(script),'--node',a.node,'--workers',str(a.workers)]
    with log.open('x') as output:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    proof=dict(status='STARTED_NOT_YET_ACCEPTED',time=stamp(),pid=process.pid,hostname=socket.gethostname(),
        node=a.node,command=command,workers=a.workers,source_sha256=sha(script),log=str(log.relative_to(ROOT)))
    atomic(marker,proof);print(json.dumps({k:proof[k] for k in ['status','pid','node','workers']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=2);main(p.parse_args())
