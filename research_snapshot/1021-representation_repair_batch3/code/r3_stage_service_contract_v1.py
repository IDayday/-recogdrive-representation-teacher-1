"""CPU concurrency/dependency contract; never touches the production queue."""
from r3_common import *
import multiprocessing as mp

FIXTURE=ROOT/'runs/stage_service_contract_v1'


def work(number):
    import r3_stage_service_v1 as service
    service.QUEUE_PATH=FIXTURE/'QUEUE.json'
    worker=dict(pid=os.getpid(),slot=number,contract_only=True)
    completed=0
    while (choice:=service.claim(worker)) is not None:
        setting,task=choice
        assert setting['id'] in {'train_a','train_b','test_locked'}
        time.sleep((number%3)*.001)
        atomic(ROOT/task['stage']/'receipts'/(task['id']+'.json'),
               dict(status='COMPLETE',worker=worker,task=task))
        completed+=1
    return completed


def main():
    assert not FIXTURE.exists(), 'Use a separate version to repeat this contract'
    settings=[]
    for name,count,size,requires in [
            ('train_a',113,3,[]),('train_b',79,4,[]),
            ('test_locked',23,2,[str((FIXTURE/'TRAIN_ACCEPTANCE.json').relative_to(ROOT))]),
            ('failed',31,3,[])]:
        stage=FIXTURE/name
        spec=dict(case_count=count,chunk_size=size,task_template=dict(cohort='CONTRACT_ONLY'))
        atomic(stage/'SPECIFICATION.json',spec)
        settings.append(dict(id=name,stage=str(stage.relative_to(ROOT)),priority=0,
            specification_sha256=sha(stage/'SPECIFICATION.json'),requires=requires))
    atomic(FIXTURE/'failed/failures/injected.json',dict(status='INJECTED_CONTRACT_FAILURE'))
    atomic(FIXTURE/'QUEUE.json',dict(open=True,stages=settings))
    production=ROOT/'runs/ELASTIC_STAGE_QUEUE.json'
    before=sha(production) if production.exists() else None
    context=mp.get_context('spawn')
    with context.Pool(12) as pool: first=pool.map(work,range(12))
    assert not (FIXTURE/'test_locked/claims').exists()
    assert not (FIXTURE/'failed/claims').exists()
    for name,count in [('train_a',113),('train_b',79)]:
        receipts=[read(p) for p in (FIXTURE/name/'receipts').glob('*.json')]
        seen=[i for row in receipts for i in row['task']['indices']]
        assert len(seen)==count and sorted(seen)==list(range(count))
        assert len(list((FIXTURE/name/'claims').iterdir()))==len(receipts)
    atomic(FIXTURE/'TRAIN_ACCEPTANCE.json',dict(status='CONTRACT_ONLY_ACCEPTANCE'))
    with context.Pool(12) as pool: second=pool.map(work,range(12))
    receipts=[read(p) for p in (FIXTURE/'test_locked/receipts').glob('*.json')]
    seen=[i for row in receipts for i in row['task']['indices']]
    assert sorted(seen)==list(range(23)) and len(seen)==23
    assert before==(sha(production) if production.exists() else None)
    atomic(FIXTURE/'PASS.json',dict(status='PASS_CPU_PARALLEL_STAGE_CONTRACT',time=stamp(),
        processes=12,first_wave_chunks=sum(first),second_wave_chunks=sum(second),
        unique_complete_indices=215,locked_test_blocked_until_explicit_acceptance=True,
        failed_stage_not_claimed=True,production_queue_unchanged=True,
        source_sha256=sha(ROOT/'code/r3_stage_service_v1.py')))
    print(json.dumps(read(FIXTURE/'PASS.json')))


if __name__=='__main__':main()
