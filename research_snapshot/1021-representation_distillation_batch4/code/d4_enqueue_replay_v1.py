"""Pause third-batch stage dispatch at committed boundaries; append replay."""
from d4_common import *
import fcntl


def main():
    smoke=read(ROOT/'provenance/TEACHER_REPLAY_SMOKE_V1.json');assert smoke['status']=='PASS_R2_FULL_CONTEXT_SMOKE'
    nodes=read(B3/'resources/REGISTRY.json')['nodes'];allocation=read(ROOT/'resources/ALLOCATION_V1.json')
    assert {n['job'] for n in nodes}=={n['job'] for n in allocation['nodes']}
    scene_path=ROOT/'manifests/R2_SCENES_V1.json';pack=B3/'teachers/first42_v1/PACK.json'
    config=dict(case_count=103288,chunk_size=8,nodes=nodes,smoke_indices=read(ROOT/'manifests/SMOKE_INDICES_V1.json'),
        task_template=dict(scenes=str(scene_path),scenes_sha256=sha(scene_path),pack=str(pack),pack_sha256=sha(pack)))
    config_path=ROOT/'configs/REPLAY_SERVICE_V1.json';assert not config_path.exists();atomic(config_path,config)
    code_hashes={p:sha(ROOT/'code'/p) for p in ['d4_common.py','d4_replay_teacher_v1.py','d4_replay_service_v1.py']}
    bridge=B3/'code/r3_batch4_replay_bridge_v1.py';stage=B3/'runs/batch4_teacher_replay_bridge_v1'
    tasks=[dict(id='batch4_teacher_replay_v1_lease%04d'%i,stage=str(stage.relative_to(B3)),handler=str(bridge.relative_to(B3)),
        handler_sha256=sha(bridge),batch4_configuration_sha256=sha(config_path),batch4_code_hashes=code_hashes) for i in range(512)]
    # Only mutable scheduling metadata is changed. Original tasks, claims,
    # receipts, outputs, specifications, and scientific code remain intact.
    from r3_common import atomic as atomic3
    with (B3/'runs/ELASTIC_STAGE_QUEUE.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);path=B3/'runs/ELASTIC_STAGE_QUEUE.json';queue=read(path)
        atomic(ROOT/'provenance/BATCH3_DISPATCH_BEFORE_PRIORITY_V1.json',queue)
        atomic3(path,dict(open=False,stages=[],time=stamp(),reason='User priority: fixed first42 H/T/HT distillation; original stages saved read-only in batch4 provenance'))
    atomic3(stage/'tasks.json',tasks);atomic3(stage/'producer.json',dict(complete=True,time=stamp(),tasks=len(tasks),batch4_teacher_replay_only=True))
    with (B3/'runs/QUEUE.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);path=B3/'runs/QUEUE.json';outer=read(path)
        assert not {v['id'] for v in outer['tasks']}&{v['id'] for v in tasks}
        outer['tasks'].extend(tasks);outer['time']=stamp();atomic3(path,outer)
    atomic(ROOT/'provenance/REPLAY_ENQUEUED_V1.json',dict(status='ENQUEUED_FULL_CONTEXT_REPLAY_ENGINEERING_FIRST',time=stamp(),
        configuration_sha256=sha(config_path),code_hashes=code_hashes,third_batch_paused_at_committed_chunk_boundaries=True,
        original_stage_queue_backup='provenance/BATCH3_DISPATCH_BEFORE_PRIORITY_V1.json',no_process_stopped=True,no_node_released=True))
    print(json.dumps(dict(status='ENQUEUED',nodes=len(nodes),devices=sum(len(n['devices']) for n in nodes),cases=103288)))


if __name__=='__main__':main()
