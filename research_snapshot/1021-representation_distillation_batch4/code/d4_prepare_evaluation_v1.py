"""Append full evaluation only after a group's declared training has finished."""
from d4_common_v2 import *
import argparse
import fcntl


def register(entries):
    lock=ROOT/'runs/EVALUATION_QUEUE.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);path=ROOT/'runs/EVALUATION_QUEUE.json';queue=read(path) if path.exists() else dict(stages=[])
        old={v['id']:v for v in queue['stages']}
        for entry in entries:
            if entry['id'] in old:assert old[entry['id']]==entry
            else:queue['stages'].append(entry)
        queue['time']=stamp();atomic(path,queue)
    service=ROOT/'code/d4_evaluation_service_v1.py';descriptor=ROOT/'runs/EVALUATION_EXECUTOR.json'
    value=dict(code=str(service.relative_to(ROOT)),sha256=sha(service),evaluator_sha256=sha(ROOT/'code/d4_evaluate_student_v1.py'))
    if descriptor.exists():assert read(descriptor)==value
    else:atomic(descriptor,value)


def engineering():
    smoke=read(ROOT/'provenance/STUDENT_FULL_EVALUATION_SMOKE_V1.json')
    assert smoke['status']=='PASS_STUDENT_CHECKPOINT_NATIVE_FULL_AND_VALID_FORMAT_EVALUATION'
    assert smoke['evaluator_sha256']==sha(ROOT/'code/d4_evaluate_student_v1.py')
    stages=[]
    for assigned in read(ROOT/'resources/ALLOCATION_V1.json')['nodes']:
        group=assigned['group'];run=ROOT/'runs'/('training_engineering_v4_'+group);complete=read(run/'TRAINING_COMPLETE.json')
        checkpoint=complete['final_matched_exposure_checkpoint'];config=ROOT/'configs/training_engineering_v4'/(group+'.json')
        index=read(ROOT/'manifests/ENGINEERING_DEVELOPMENT_16_V1.json')[:2]
        node=next(n for n in read(B3/'resources/REGISTRY.json')['nodes'] if n['name']==assigned['node'])
        stage=ROOT/'runs/evaluation_engineering_v1'/group
        spec=dict(indices=index,devices=node['devices'],lanes_per_device=4,golden_development_stage=str((run/'development/epoch02').relative_to(ROOT)),
            task_template=dict(cohort='navtrain',noises=list(range(10)),model_id='engineering_'+group+'_epoch2',
                checkpoint=str(ROOT/checkpoint['path']),checkpoint_sha256=checkpoint['sha256'],training_config=str(config),training_config_sha256=sha(config)))
        path=stage/'SPECIFICATION.json'
        if path.exists():assert read(path)==spec
        else:atomic(path,spec)
        stages.append(dict(id='evaluation_engineering_v1_'+group,group=group,kind='engineering',priority=0,stage=str(stage.relative_to(ROOT)),
            specification_sha256=sha(path),requires=['runs/distillation_main_v4_'+group+'/TRAINING_COMPLETE.json']))
    register(stages);print(json.dumps(dict(status='ENGINEERING_REGISTERED_AFTER_OWN_GROUP_TRAINING',groups=3,actual_test_used=False)))


def formal(group):
    import numpy as np
    run=ROOT/'runs'/('distillation_main_v4_'+group);complete=read(run/'TRAINING_COMPLETE.json')
    config_path=ROOT/'configs/distillation_main_v4'/(group+'.json');config=read(config_path)
    assert complete['status']=='ALL_RANKS_TRAINING_COMPLETE_REQUIRES_FULL_EVALUATION' and complete['configuration_sha256']==sha(config_path)
    assert (ROOT/'runs/evaluation_engineering_v1'/group/'AGENT_ACCEPTANCE.json').exists()
    for rank in range(config['world_size']):
        proof=read(run/'ranks'/('rank%02d'%rank)/'TRAINING_COMPLETE.json')
        assert proof['optimizer_steps']==6670 and proof['configuration_sha256']==sha(config_path) and proof['frozen_original_parameters_unchanged']
    protocol_path=ROOT/'provenance/FROZEN_EVALUATION_PROTOCOL_V1.json';protocol=read(protocol_path)
    candidates={}
    for role,reference in [('primary_final',complete['final_matched_exposure_checkpoint']),('secondary_development_best',complete['best']['checkpoint'])]:
        assert sha(ROOT/reference['path'])==reference['sha256']
        candidates.setdefault(reference['sha256'],dict(reference=reference,roles=[]))['roles'].append(role)
    stages=[];models=[]
    for order,(hashed,value) in enumerate(candidates.items()):
        reference=value['reference'];model_id='student_'+group+'_'+hashed[:16]
        lock_path=ROOT/'provenance/student_test_locks_v1'/(model_id+'.json')
        lock=dict(status='FROZEN_MODEL_BEFORE_TEST',group=group,model_id=model_id,roles=value['roles'],checkpoint_sha256=hashed,
            training_config_sha256=sha(config_path),protocol_sha256=sha(protocol_path),test_rows_sha256=protocol['test_rows_sha256'],
            noises=list(range(10)),model_choice_uses_test_or_new_noise=False,GT_used=False)
        if lock_path.exists():assert read(lock_path)==lock
        else:atomic(lock_path,lock)
        model=dict(id=model_id,group=group,roles=value['roles'],checkpoint=reference,training_config=str(config_path),training_config_sha256=sha(config_path),test_lock=str(lock_path),test_lock_sha256=sha(lock_path))
        models.append(model)
        for position,(cohort,tag,count,noises) in enumerate([
            ('navtrain','navtrain_S0S4',103288,list(range(5))),('navtrain','validation_S5S9',17475,list(range(5,10))),
            ('navtest','navtest_S0S9',12146,list(range(10)))]):
            ident=model_id+'_'+tag;stage=ROOT/'runs/full_student_evaluation_v1'/ident
            task=dict(cohort=cohort,noises=noises,model_id=model_id,checkpoint=str(ROOT/reference['path']),checkpoint_sha256=hashed,
                training_config=str(config_path),training_config_sha256=sha(config_path),test_lock=str(lock_path),test_lock_sha256=sha(lock_path))
            spec=dict(case_count=count,chunk_size=8,task_template=task,model_roles=value['roles'])
            if tag=='validation_S5S9':
                indices=ROOT/'manifests/VALIDATION_INDICES_V1.json';assert len(read(indices))==count
                spec.update(indices_path=str(indices),indices_sha256=sha(indices))
            path=stage/'SPECIFICATION.json'
            if path.exists():assert read(path)==spec
            else:atomic(path,spec)
            requires=['runs/evaluation_engineering_v1/'+group+'/AGENT_ACCEPTANCE.json']
            if cohort=='navtest':requires.append('runs/full_student_evaluation_v1/'+model_id+'_navtrain_S0S4/AGENT_ACCEPTANCE.json')
            stages.append(dict(id=ident,group=group,kind='formal',priority=10+order*10+position,stage=str(stage.relative_to(ROOT)),
                specification_sha256=sha(path),requires=requires))
    register(stages)
    path=ROOT/'runs'/('FROZEN_EVALUATION_MODELS_'+group+'.json')
    value=dict(status='FROZEN_MODEL_SET_FOR_EVALUATION',group=group,models=models,protocol_sha256=sha(protocol_path),source_training_complete_sha256=sha(run/'TRAINING_COMPLETE.json'))
    if path.exists():assert read(path)==value
    else:atomic(path,value)
    print(json.dumps(dict(status='FORMAL_EVALUATION_REGISTERED',group=group,unique_checkpoints=len(models),stages=len(stages))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engineering',action='store_true');p.add_argument('--group',choices=['H','T','HT']);a=p.parse_args()
    if a.engineering:engineering()
    else:assert a.group;formal(a.group)
