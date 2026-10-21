"""Launch the task-private CPU evaluator auditor once on its verified node."""
from d4_common_v2 import *
import argparse
import fcntl
import socket
import subprocess


def main(a):
    node=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    folder=ROOT/'runs/evaluation_auditor_launches_v1';folder.mkdir(parents=True,exist_ok=True)
    with (folder/(a.node+'.lock')).open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        marker=folder/(a.node+'.json');assert not marker.exists(), 'Review an existing launch rather than start a second auditor'
        source=ROOT/'code/d4_evaluation_audit_guard_v1.py';auditor=ROOT/'code/d4_evaluation_audit_v1.py'
        log=ROOT/'runs/evaluation_auditor_logs_v1'/(a.node+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,'-u','-B',str(source),'--node',a.node,'--workers',str(a.workers)]
        with log.open('x') as output:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        atomic(marker,dict(status='STARTED_AWAITING_HEARTBEAT',time=stamp(),node=a.node,job=node['job'],pid=process.pid,
            workers=a.workers,command=command,log=str(log.relative_to(ROOT)),source_sha256=sha(source),auditor_sha256=sha(auditor)))
        print(json.dumps(dict(status='STARTED',node=a.node,pid=process.pid,workers=a.workers)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();assert 1<=a.workers<=16;main(a)
