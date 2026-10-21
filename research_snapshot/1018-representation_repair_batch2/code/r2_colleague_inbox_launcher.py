"""Independent job-bound handoff inbox; never reads the research task queue."""
from r2_common import *
import subprocess

DEST=ROOT/'resources/handoffs/peer_b1_20261019/colleague_launcher'
JOB='dlcqdtslnqnytsc7'


def main():
    setup('colleague_launcher/peer_b1')
    assert socket.gethostname().startswith(JOB+'-')
    DEST.mkdir(parents=True,exist_ok=True)
    guard=(DEST/'launcher.lock').open('a+');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    processes={};handles=[]
    while True:
        accepted=(DEST.parent/'ACCEPTED_EMPTY_FOR_OWNER.json').exists()
        activation=DEST/'OWNER_ACTIVATION.json'
        authorized=accepted and activation.exists()
        if authorized:
            lease=read(activation);assert lease['expected_job']==JOB
            ownerroot=Path(lease['task_root']).resolve()
            assert ownerroot.is_relative_to('/mnt/workspace') and ownerroot!=Path('/mnt/workspace')
            for path in sorted((DEST/'pending').glob('*.json')):
                receipt=DEST/'receipts'/path.name
                if receipt.exists():continue
                c=read(path);assert c['expected_job']==JOB
                script=Path(c['script']).resolve();cwd=Path(c['cwd']).resolve()
                assert script.is_relative_to(ownerroot) and cwd.is_relative_to(ownerroot)
                assert sha(script)==c['script_sha256'] and script.suffix in ['.py','.sh']
                assert isinstance(c.get('arguments',[]),list) and all(isinstance(v,str) for v in c.get('arguments',[]))
                env=c.get('env',{});assert set(env)<={'CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONPATH'}
                log=DEST/'logs'/(path.stem+'.log');log.parent.mkdir(parents=True,exist_ok=True)
                handle=log.open('a');handles.append(handle)
                argv=([sys.executable,'-u','-B'] if script.suffix=='.py' else ['bash'])+[str(script),*c.get('arguments',[])]
                p=subprocess.Popen(argv,cwd=cwd,env=dict(os.environ,**env),stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                processes[path.name]=p
                atomic(receipt,dict(status='LAUNCHED',time=stamp(),expected_job=JOB,pid=p.pid,command_sha256=sha(path),log=str(log)))
        for name,p in processes.items():
            rc=p.poll();atomic(DEST/'states'/name,dict(status='RUNNING' if rc is None else 'COMPLETE' if rc==0 else 'FAILED',time=stamp(),pid=p.pid,returncode=rc))
        atomic(DEST/'LIVE.json',dict(time=stamp(),job=JOB,pid=os.getpid(),status='READY' if authorized else 'WAITING_OWNER_ACTIVATION',
            independent_queue=True,scientific_tasks_not_inherited=True,cloud_stop_or_release_supported=False))
        time.sleep(15)


if __name__=='__main__':main()
