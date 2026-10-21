"""Start a separate frozen program inside retained containers, leaving original coordinators alive."""
from common import *
import argparse
import subprocess

def main(args):
    setup(f'repair/remote_start/{args.run}/node{args.node}')
    expected=['dlc1whaxhnd8c2zs-master-0','dlc1whaxhnnaj1nn-master-0'][args.node]
    assert os.uname().nodename==expected,'Must execute inside the verified retained container'
    import torch
    assert torch.cuda.is_available() and torch.cuda.device_count()==16
    primary=[]
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():continue
        try:parts=(item/'cmdline').read_bytes().split(b'\0')
        except (OSError,PermissionError):continue
        if any(p.endswith(b'/repair_queue_v2.py') or p==b'code/repair_queue_v2.py' for p in parts) and b'node' in parts:
            primary.append(int(item.name))
    assert len(primary)==1,primary
    execution=read(ROOT/args.execution);assert execution['run']==args.run
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    base=ROOT/'runs'/args.run;folder=base/f'node{args.node}';folder.mkdir(parents=True,exist_ok=True)
    proof=folder/'AUXILIARY_STARTED.json';assert not proof.exists(),'Do not launch duplicate auxiliary coordinators'
    program=(ROOT/args.program).resolve();assert program.is_relative_to(ROOT/'code')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    env['PYTHONPATH']=str(ROOT/'code')+(':'+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    command=[sys.executable,'-B',str(program),'node','--node',str(args.node),'--run',args.run,'--execution',str(ROOT/args.execution)]
    log=folder/'auxiliary_launcher.log'
    with log.open('x') as output:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    time.sleep(1);assert child.poll() is None,('Auxiliary exited during startup',child.returncode,str(log))
    value=dict(status='STARTED',time=stamp(),node=args.node,hostname=expected,auxiliary_pid=child.pid,primary_coordinator_pid=primary[0],
        primary_preserved=True,program_sha256=sha(program),execution_sha256=sha(ROOT/args.execution),command=command,log=str(log))
    atomic(proof,value);print(json.dumps(value),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,required=True,choices=[0,1]);p.add_argument('--run',required=True)
    p.add_argument('--execution',required=True);p.add_argument('--program',default='code/repair_final_queue.py');main(p.parse_args())
