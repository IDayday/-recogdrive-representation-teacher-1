"""Launch one H/T/HT group on a configurable single-node CUDA topology."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--config',required=True);p.add_argument('--resume');p.add_argument('--devices',default='0,1,2,3,4,5,6,7')
    p.add_argument('--mode',choices=['preflight','train'],required=True);p.add_argument('--port',type=int,default=29571)
    p.add_argument('--fresh',action='store_true')
    a=p.parse_args();devices=a.devices.split(',');config=json.loads(Path(a.config).read_text())
    if len(devices)!=config['world_size'] or len(set(devices))!=len(devices):raise ValueError('Distinct device count must match the config')
    if a.mode=='train':
        if bool(a.resume)==bool(a.fresh):raise ValueError('Choose exactly one of --fresh or --resume')
        if a.fresh:
            if not config.get('portable_fresh'):raise ValueError('Fresh start requires an explicit fresh configuration')
            from continuation.layout import BATCHES
            run=Path(a.workspace)/BATCHES[3]/'runs'/config['run_id']
            if (run/'checkpoints').exists():raise ValueError('Existing training checkpoints found; resume or choose a new run')
    command=[sys.executable,'-B','-m','torch.distributed.run','--nnodes=1',f'--nproc_per_node={len(devices)}',
        f'--master_port={a.port}','-m','continuation.worker','--paths',str(Path(a.paths).resolve()),
        '--workspace',str(Path(a.workspace).resolve()),'--config',str(Path(a.config).resolve()),'--mode',a.mode]
    if a.resume:command+=['--resume',str(Path(a.resume).resolve())]
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=a.devices,PYTHONDONTWRITEBYTECODE='1')
    raise SystemExit(subprocess.run(command,env=env).returncode)

if __name__=='__main__':main()
