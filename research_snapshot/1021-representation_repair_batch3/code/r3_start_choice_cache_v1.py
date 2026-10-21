"""Start a bounded CPU-only numeric cache on a verified owned node."""
from r3_common import *
import argparse
import socket
import subprocess


def main(a):
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    folder=ROOT/'runs/first42_selected_edit_cache_v1'/a.cohort;marker=folder/'LAUNCH.json';assert not marker.exists()
    folder.mkdir(parents=True,exist_ok=True)
    script=ROOT/'code/r3_cache_first42_edits_v1.py'
    command=[sys.executable,'-u','-B',str(script),'--cohort',a.cohort,'--workers',str(a.workers),'--output','analysis/first42_selected_edits_v1/'+a.cohort]
    with (folder/'stdout.log').open('x') as log:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    atomic(marker,dict(status='STARTED_CPU_ANALYSIS_ONLY',time=stamp(),node=a.node,job=node['job'],pid=process.pid,
        command=command,source_sha256=sha(script),GPU_used=False,new_teacher_snapshot_created=False))
    print(json.dumps(dict(status='STARTED',node=a.node,pid=process.pid,CPU_workers=a.workers,cohort=a.cohort)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--cohort',choices=['navtrain','navtest'],required=True)
    p.add_argument('--workers',type=int,default=4);main(p.parse_args())
