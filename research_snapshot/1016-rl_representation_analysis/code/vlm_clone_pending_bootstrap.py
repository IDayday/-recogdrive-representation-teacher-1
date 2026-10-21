"""A queued clone waits for actual startup, then checks and joins independently."""
from common import *
import argparse,subprocess
from vlm_elastic_registry import DEST,configuration

def run(script,args):
    subprocess.run([sys.executable,'-u','-B',str(ROOT/'code'/script),*args],cwd=ROOT,check=True)

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];end=time.monotonic()+3600
    for name in ['EXECUTION.json','CLONE_EXECUTION.json','CLONE_ADMIN_EXECUTION.json','CLONE_PHASE_EXECUTION.json','GPU_PROGRESS_CHECK_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    while not all((folder/name).exists() for name in ['LAUNCHED.json','PREFLIGHT.json','CPU_SMOKE_PASS.json','GPU_SMOKE_PASS.json','ENGINEERING_PASS.json']):
        assert not list((folder/'failures').glob('*.json'))
        assert not list((folder/'clone_wrapper_failures').glob('*.json'))
        assert time.monotonic()<end,'New clone startup exceeded one hour; preserve original errors and container.'
        time.sleep(5)
    run('vlm_clone_phase_check.py',['--id',a.id])
    run('vlm_clone_gpu_activate.py',['--id',a.id])
    run('vlm_clone_gpu_progress_check.py',['--id',a.id])
    print('PENDING_CLONE_STARTUP_AND_REAL_QUEUE_ACCEPTANCE_PASS',a.id,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);main(p.parse_args())
