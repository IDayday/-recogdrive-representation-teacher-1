"""Freeze independent Gaussian null validation; reuses retained jobs, no cloud mutations."""
from common import *
from repair_validation_null_queue import stage

def main():
    setup('repair/null_prepare')
    run='repair_null_validation_20261016_v1';base=ROOT/'runs'/run
    assert not base.exists()
    proof=ROOT/'runs/repair_null_dsw_v2/smoke/rank000.json';assert read(proof)['status']=='PASS'
    count=stage(base,'validation_true_random',read(ROOT/'repair_v1/validation.json'),read(ROOT/'repair_v1/true_random_arms.json'),[0,1,2],chunk=16)
    old=read(ROOT/'configs/repair_execution_v2.json')
    paths=set(old['code_sha256'])-{'code/repair_queue_v2.py','code/repair_launch_v2.sh'}
    paths.update(['code/repair_true_random.py','code/repair_validation_null_queue.py'])
    cfg=dict(time=stamp(),run=run,code_sha256={p:sha(ROOT/p) for p in sorted(paths)},
        dsw_reference=str(proof.relative_to(ROOT)),submissions=old['submissions'],resources=old['resources'],
        initial_tasks_sha256=sha(base/'tasks.json'),parent_execution_sha256=sha(ROOT/'configs/repair_execution_v2.json'),
        true_random_protocol_sha256=sha(ROOT/'repair_v1/TRUE_RANDOM_PROTOCOL.json'),
        scheduling='Independent UUID/mkdir queue; existing two jobs retained; start only after parent compute drains',
        role='controls only, not eligible for candidate selection',retain_resources=True)
    cfg['identity']=digest(cfg);atomic(ROOT/'configs/repair_null_execution_v1.json',cfg)
    atomic(ROOT/'repair_v1/TRUE_RANDOM_READY.json',dict(status='FROZEN',time=stamp(),run=run,tasks=count,execution_sha256=sha(ROOT/'configs/repair_null_execution_v1.json'),smoke_sha256=sha(proof)))
    print(json.dumps(dict(status='NULL_READY',run=run,tasks=count)))

if __name__=='__main__':main()
