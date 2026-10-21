"""Start this task's CPU auditor once on an identity-verified node."""
from d4_common import *
import argparse
import socket
import subprocess


def main(a):
    node=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    marker=ROOT/'runs/replay_auditor_launches_v1'/(a.node+'.json');assert not marker.exists()
    script=ROOT/'code/d4_audit_replay_v1.py';log=ROOT/'runs/replay_auditor_logs_v1'/(a.node+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-u','-B',str(script),'--node',a.node,'--workers','4']
    with log.open('x') as output:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    atomic(marker,dict(status='STARTED_NOT_YET_ACCEPTED',time=stamp(),node=a.node,pid=process.pid,command=command,log=str(log.relative_to(ROOT)),source_sha256=sha(script)))
    print(json.dumps(dict(status='STARTED',node=a.node,pid=process.pid)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
