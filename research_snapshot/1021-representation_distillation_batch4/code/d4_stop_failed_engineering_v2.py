"""Stop only verified failed v2 smoke ranks and their captured descendants."""
from d4_common import *
import argparse
import socket


def main(a):
    import psutil
    group=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(group['job']+'-')
    run=ROOT/'runs'/('training_engineering_v2_'+group['group']);launch=read(run/'LAUNCH.json')
    assert not list((run/'checkpoints').glob('*.pt')) and not list((run/'ranks').glob('*/LIVE.json'))
    assert 'AF_UNIX path too long' in (run/'logs/rank00.log').read_text()
    processes={};evidence=[]
    for child in launch['children']:
        try:parent=psutil.Process(child['pid']);command=parent.cmdline()
        except (psutil.NoSuchProcess,psutil.ZombieProcess):continue
        assert command==child['command'] and str(ROOT/'code/d4_train_v2.py') in command and launch['run'] in command
        family=[parent]+parent.children(recursive=True)
        evidence.append(dict(rank=child['rank'],root_pid=parent.pid,command=command,descendant_pids=[p.pid for p in family[1:]]))
        for process in family:
            try:processes[process.pid]=(process,process.create_time())
            except (psutil.NoSuchProcess,psutil.ZombieProcess):pass
    # All roots are verified before any signal. No original resident worker or
    # DLC parent belongs to these independent smoke process subtrees.
    stopped=[]
    for pid,(process,created) in processes.items():
        try:
            if process.create_time()==created:process.terminate();stopped.append(pid)
        except (psutil.NoSuchProcess,psutil.ZombieProcess):pass
    gone,alive=psutil.wait_procs([p for p,_ in processes.values()],timeout=10)
    forced=[]
    for process in alive:
        try:
            if process.create_time()==processes[process.pid][1]:process.kill();forced.append(process.pid)
        except (psutil.NoSuchProcess,psutil.ZombieProcess):pass
    psutil.wait_procs(alive,timeout=5)
    proof=dict(status='FAILED_V2_ENGINEERING_ONLY_PROCESS_SUBTREES_STOPPED',time=stamp(),node=a.node,run=launch['run'],verified_roots=evidence,
        terminated_pids=stopped,forced_after_timeout=forced,no_committed_optimizer_steps=True,no_DLC_or_resident_main_process_signalled=True,
        original_logs_and_outputs_preserved=True,reason='Private TMPDIR generated AF_UNIX socket path over the platform limit')
    atomic(ROOT/'provenance'/('ENGINEERING_V2_STOP_'+a.node+'.json'),proof)
    print(json.dumps(dict(status=proof['status'],node=a.node,verified_roots=len(evidence),stopped=len(stopped),forced=len(forced))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
