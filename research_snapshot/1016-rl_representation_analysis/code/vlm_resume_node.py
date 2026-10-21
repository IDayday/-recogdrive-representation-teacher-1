"""Task-owned restart master; retaining the main process never depends on a child exit."""
from common import *
import argparse,subprocess,traceback
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT

def main(a):
    setup(f'vlm_repair/resume/node{a.node}');folder=ROOT/a.resume/f'node{a.node}';folder.mkdir(exist_ok=True)
    assert read(ROOT/a.resume/'PREPARED.json')['status']=='PREPARED_NOT_SUBMITTED'
    p=read(VOUT/'RESUME_EXECUTION.json')
    for path,h in p['code_sha256'].items():assert sha(ROOT/path)==h,path
    from natural_coordinate import preflight
    class Args:pass
    args=Args();args.node=a.node;args.run='vlm_resume_'+Path(a.resume).name
    preflight(args,dict(p,identity='Same frozen RL/VLM data and seeds; continuation after actual platform termination'))
    names={
        'repair_original':['vlm_repair_queue_v6.py','node','--node',str(a.node),'--workers','16','--run','vlm_repair_20261016_v2'],
        'repair_next_waiter':['vlm_wait_launch_v6.py','--node',str(a.node)],
        'scan':['vlm_scan_queue.py','node','--node',str(a.node),'--workers','16','--threads','4'],
        'canonical_scan':['vlm_core_scan.py','node','--node',str(a.node)],
        'controllers':['vlm_controller_host_v2.py','--node',str(a.node)],
        'semantic_gap':['vlm_semantic_collect.py','node','--node',str(a.node)],
        'semantic_rapid':['vlm_semantic_cpu.py','node','--node',str(a.node),'--kind','rapid','--workers','8'],
        'semantic_scan':['vlm_semantic_cpu.py','node','--node',str(a.node),'--kind','scan','--workers','8']}
    if a.node==0:names['semantic_analysis']=['vlm_semantic_analysis.py']
    else:
        names['final_driver']=['vlm_final_driver.py']
        names['semantic_repair']=['vlm_semantic_repair_v3.py']
    processes={};streams={};env=dict(os.environ)
    for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
    for name,command in names.items():
        stream=(folder/(name+'.log')).open('a');streams[name]=stream
        processes[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code'/command[0])]+command[1:],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
    atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),node=a.node,processes={n:p.pid for n,p in processes.items()}))
    while True:
        state={name:dict(pid=p.pid,returncode=p.poll(),status='RUNNING' if p.poll() is None else 'COMPLETE' if p.returncode==0 else 'FAILED') for name,p in processes.items()}
        for name,s in state.items():
            if s['status']=='FAILED':atomic(folder/'failures'/(name+'.json'),dict(time=stamp(),original_log=str((folder/(name+'.log')).relative_to(ROOT)),**s))
        atomic(folder/'STATUS.json',dict(time=stamp(),node=a.node,processes=state,main_process_retained=True))
        time.sleep(30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);p.add_argument('--resume',required=True);a=p.parse_args()
    try:main(a)
    except BaseException as e:
        atomic(ROOT/a.resume/f'node{a.node}/FAILED.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()))
        # Preserve the allocated task for inspection; only the platform hard cap ends it.
        while True:time.sleep(30)
