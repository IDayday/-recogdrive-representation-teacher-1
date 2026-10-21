"""Clone identity lease, shared-filesystem heartbeat, and scoped command inbox."""
from common import *
import argparse,fcntl,socket,re,subprocess,traceback
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];setup('vlm_repair/clone/'+a.id)
    for p,h in read(DEST/'CLONE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    host=socket.gethostname();match=re.match(r'^(dlc[a-zA-Z0-9]+)(?:-|$)',host);assert match,host
    job=match.group(1);attest=folder/'attestations'/job;attest.mkdir(parents=True,exist_ok=True)
    with (attest/'runtime.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic(attest/'IDENTITY.json',dict(status='CONTAINER_STARTED',time=stamp(),job=job,hostname=host,node=a.id,
            pid=os.getpid(),config_sha256=sha(folder/'CONFIG.json'),requested_max_minutes=c['max_running_minutes'],
            actual_server_max_minutes_not_inferred=True))
        core=None;streams=[];commands={}
        while True:
            activation=folder/'CLONE_ACTIVATION.json';authorized=activation.exists() and read(activation)['job']==job
            if authorized and core is None:
                lease=read(activation);assert lease['confirmed_max_minutes']>=4320
                stream=(attest/'node_runtime.log').open('a');streams.append(stream)
                core=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_node.py'),'node','--id',a.id],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
                atomic(attest/'CORE_LAUNCHED.json',dict(status='PASS',time=stamp(),pid=core.pid,job=job,
                    activation_sha256=sha(activation),new_node_runtime_source_sha256=sha(ROOT/'code/vlm_elastic_node.py')))
            if authorized:
                for p in sorted((folder/'commands/pending').glob('*.json')):
                    command=read(p);assert command['expected_job']==job
                    receipt=folder/'commands/receipts'/p.name
                    if receipt.exists():continue
                    script=(ROOT/command['script']).resolve();assert script.is_relative_to(ROOT/'code')
                    assert sha(script)==command['source_sha256']
                    assert set(command.get('env',{}))<={'CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'}
                    assert isinstance(command['arguments'],list) and all(isinstance(x,str) for x in command['arguments'])
                    stream=(folder/'commands/logs'/(p.stem+'.log'));stream.parent.mkdir(parents=True,exist_ok=True);handle=stream.open('a');streams.append(handle)
                    child=subprocess.Popen([sys.executable,'-u','-B',str(script),*command['arguments']],cwd=ROOT,
                        env=dict(os.environ,**command.get('env',{})),stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                    commands[p.name]=child
                    atomic(receipt,dict(status='LAUNCHED',time=stamp(),job=job,pid=child.pid,command_sha256=sha(p),source_sha256=sha(script)))
                for name,p in commands.items():
                    rc=p.poll();atomic(folder/'commands/states'/name,dict(status='RUNNING' if rc is None else 'COMPLETE' if rc==0 else 'FAILED',time=stamp(),job=job,pid=p.pid,returncode=rc))
                    if rc not in [None,0]:atomic(folder/'command_failures'/name,dict(status='FAILED',time=stamp(),job=job,pid=p.pid,returncode=rc,log=str((folder/'commands/logs'/(Path(name).stem+'.log')).relative_to(ROOT))))
            rc=core.poll() if core is not None else None
            if core is not None and rc is not None:
                atomic(attest/'CORE_EXIT.json',dict(status='EXITED',time=stamp(),job=job,pid=core.pid,returncode=rc))
            atomic(attest/'LIVE.json',dict(status='RUNNING' if core is not None and rc is None else 'WAITING_IDENTITY_BINDING' if core is None else 'CORE_EXITED_CONTAINER_RETAINED',
                time=stamp(),job=job,node=a.id,hostname=host,pid=os.getpid(),core_pid=core.pid if core is not None else None,
                authorized_clone_identity=authorized,shared_command_inbox=True,main_retained=True))
            time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        c=configuration(a.id);folder=ROOT/c['folder'];host=socket.gethostname()
        atomic(folder/'clone_wrapper_failures'/(host+'.json'),dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        while True:time.sleep(30)
