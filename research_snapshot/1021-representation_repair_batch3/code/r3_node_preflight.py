"""Read-only real-container inventory; no scientific worker signals."""
from r3_common import *
import argparse
import importlib.metadata
import socket
import subprocess


def main(args):
    setup('preflight/' + args.node)
    import psutil
    import torch
    assert socket.gethostname().startswith(args.job + '-')
    processes = []
    for p in psutil.process_iter(['pid', 'ppid', 'cmdline', 'create_time', 'status', 'uids']):
        try:
            command = p.info['cmdline'] or []
            if any(x.startswith(str(BATCH2/'code') + '/') or x.startswith(str(ROOT/'code') + '/') for x in command):
                processes.append(dict(pid=p.pid, ppid=p.ppid(), cmdline=command, created=p.create_time(), status=p.status(), uid=p.uids().real))
        except psutil.NoSuchProcess: pass
    devices = []
    for i in range(torch.cuda.device_count()):
        prop = torch.cuda.get_device_properties(i)
        devices.append(dict(device=i, name=prop.name, total_memory=prop.total_memory))
    mounts = {p: subprocess.check_output(['findmnt', '-T', p, '-n', '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS'], text=True).strip()
              for p in ['/mnt/workspace', '/mnt/data', '/mnt/yehr_workspace']}
    versions = {}
    for package in ['torch','torchvision','numpy','transformers','timm','diffusers','scipy','nuplan-devkit']:
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = None
    assert devices and psutil.virtual_memory().available > 32 * 1024**3
    out = dict(status='PASS_ENVIRONMENT_NOT_MODEL_SMOKE', time=stamp(), node=args.node, job=args.job,
               hostname=socket.gethostname(), cpu_affinity=len(os.sched_getaffinity(0)),
               memory_available=psutil.virtual_memory().available, devices=devices, mounts=mounts,
               versions=versions, existing_research_processes=processes, no_process_signals=True)
    atomic(ROOT/'resources/nodes'/args.node/'PREFLIGHT.json', out)
    print(json.dumps({k:out[k] for k in ['status','node','job','cpu_affinity','memory_available','devices']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--node',required=True); p.add_argument('--job',required=True)
    main(p.parse_args())
