"""Add isolated CPU producers to verified existing containers; retain all queues."""
from common import *
import argparse,subprocess,traceback
from vlm_core import VOUT
from vlm_late_qualification import DEST
from repair_queue_v2 import atomic_unique as atomic


def main(a):
    setup('vlm_repair/late_services')
    import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    folder=ROOT/a.resume/'late_services'/f'node{a.node}'
    folder.mkdir(parents=True,exist_ok=False)
    for p,h in read(VOUT/'LATE_SERVICES_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    names={'qualifiers':['vlm_late_selection.py','node','--node',str(a.node),'--workers','16',
            '--threads','2','--launch',str((folder/'qualifiers').relative_to(ROOT))]}
    if a.node==1:names.update(selector=['vlm_late_selection.py','controller'],repair=['vlm_late_repair.py'])
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),node=a.node,
        cpu=os.cpu_count(),available_memory=psutil.virtual_memory().available,commands=names,
        qualifications_wait_for_full_grid=True,new_gpu_workers=0,retains_all_original_processes=True))
    children={};streams=[]
    for name,cmd in names.items():
        stream=(folder/(name+'.log')).open('a');streams.append(stream)
        children[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code'/cmd[0])]+cmd[1:],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10))
    while True:
        states={n:dict(pid=p.pid,returncode=p.poll()) for n,p in children.items()}
        bad={n:s for n,s in states.items() if s['returncode'] not in [None,0]}
        assert not bad,bad
        atomic(folder/'STATUS.json',dict(time=stamp(),states=states,original_processes_untouched=True))
        time.sleep(30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True)
    p.add_argument('--resume',required=True);a=p.parse_args()
    try:main(a)
    except BaseException as e:
        atomic(DEST/'failures'/f'services_node{a.node}.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
