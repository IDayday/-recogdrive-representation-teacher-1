"""Validate exact threshold reuse before adopting independent evaluator version."""
from r2_common import *
from r2_resume_support import register_once


def main():
    tests=[]
    for kind in ['hard_continuous','soft_joint']:
        found=None
        for path in (ROOT/'behavior_routers').glob('*/TRAINING.json'):
            model=read(path)
            if model.get('system')=='representation_K2_seed0' and model.get('heldout_fold')==-1 and model['kind']==kind and len(model['checkpoints'])==2:
                found=str(path.relative_to(ROOT));break
        assert found,'Preexisting actual trained interface policy missing'
        tests.append(dict(training_path=found,raw=False))
        path=ROOT/'behavior_routers'/('raw_multisite_router_smoke_v1_'+kind)/'TRAINING.json';assert path.exists()
        tests.append(dict(training_path=str(path.relative_to(ROOT)),raw=True,prepare_two_checkpoints=True))
    smoke=ROOT/'runs/joint_threshold_reuse_smoke_v1';panel=read(ROOT/'runs/raw_multisite_router_smoke_v1/tasks.json')[0]['panel']
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='joint_threshold_reuse_smoke_v1',stage=str(smoke.relative_to(ROOT)),tests=tests,panel=panel)]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    handler='code/r2_joint_memo_smoke.py';register_once(dict(name='joint_threshold_reuse_four_way_exact_AB',path=str(smoke.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not (ROOT/'provenance/JOINT_THRESHOLD_REUSE_ENGINEERING_PASS.json').exists():time.sleep(15)
    assert read(ROOT/'provenance/JOINT_THRESHOLD_REUSE_ENGINEERING_PASS.json')['all_record_fields_exact']
    for stage in ['behavior_router_quick_v1','additional_joint_quick_v1']:
        handler='code/r2_joint_eval_memo_v2.py'
        register_once(dict(name=stage+'_verified_threshold_reuse',path='runs/'+stage,handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=23.71,enabled=False))
    atomic(ROOT/'provenance/JOINT_THRESHOLD_REUSE_ADOPTION.json',dict(time=stamp(),proof='provenance/JOINT_THRESHOLD_REUSE_ENGINEERING_PASS.json',
        stages=['behavior_router_quick_v1','additional_joint_quick_v1'],scientific_protocol_and_canonical_claims_unchanged=True,existing_inflight_unchanged=True,
        actual_rollout_and_independent_score_reused=True,logical_records_preserved=True))


if __name__=='__main__':main()
