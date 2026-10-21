"""Start final locked program on the retained nodes once null compute drains."""
from common import *
from repair_terminal import execute

def main():
    setup('repair/final_transition')
    parent=ROOT/'runs/repair_null_validation_20261016_v1'
    while not (parent/'COMPUTE_DRAINED_RESOURCES_HELD.json').exists() or not (ROOT/'repair_v1/FINAL_TEST_READY.json').exists():
        print(json.dumps(dict(status='WAIT_NULL_AND_FINAL_SMOKE',time=stamp())),flush=True);time.sleep(60)
    cfg=read(ROOT/'configs/repair_final_execution_v1.json')
    for node,job in enumerate(['dlc1whaxhnd8c2zs','dlc1whaxhnnaj1nn']):
        command=f'cd {ROOT} && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /usr/local/bin/python -B code/repair_remote_start.py --node {node} --run {cfg["run"]} --execution configs/repair_final_execution_v1.json --program code/repair_final_queue.py'
        proof=execute(job,command);atomic(ROOT/f'provenance/final_start_node{node}.json',proof);assert proof['exit_code']==0
        print(json.dumps(dict(status='FINAL_STARTED',node=node,time=stamp())),flush=True)

if __name__=='__main__':main()
