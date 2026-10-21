"""Keep foreground wait and start prepared null workload when parent computation drains."""
from common import *
from repair_terminal import execute

def main():
    setup('repair/null_transition')
    parent=ROOT/'runs/repair_20261016_v2';ready=parent/'COMPUTE_DRAINED_RESOURCES_HELD.json'
    while not ready.exists():
        assert not list((parent/'failures').glob('*.json'))
        print(json.dumps(dict(status='WAIT_PARENT_DRAIN',time=stamp())),flush=True);time.sleep(60)
    tasks=read(parent/'tasks.json');assert all((parent/'receipts'/f'{t["id"]}.json').exists() for t in tasks)
    assert not read(parent/'queue.json')['closed']
    for node,job in enumerate(['dlc1whaxhnd8c2zs','dlc1whaxhnnaj1nn']):
        command=f'cd {ROOT} && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /usr/local/bin/python -B code/repair_remote_start.py --node {node} --run repair_null_validation_20261016_v1 --execution configs/repair_null_execution_v1.json --program code/repair_validation_null_queue.py'
        proof=execute(job,command);atomic(ROOT/f'provenance/null_start_node{node}.json',proof);assert proof['exit_code']==0
        print(json.dumps(dict(status='NULL_STARTED',node=node,time=stamp())),flush=True)
    print(json.dumps(dict(status='TRANSITION_COMPLETE',time=stamp())),flush=True)

if __name__=='__main__':main()
