"""Return a node to batch three only after all its frozen student evaluations pass."""
from d4_common_v2 import *
import argparse


def main(a):
    group=a.group;run=ROOT/'runs'/('distillation_main_v4_'+group)
    training=read(run/'TRAINING_AGENT_ACCEPTANCE.json');assert training['status']=='PASS_COMPLETE_MATCHED_EXPOSURE_DDP_TRAINING'
    frozen_path=ROOT/'runs'/('FROZEN_EVALUATION_MODELS_'+group+'.json');frozen=read(frozen_path)
    protocol_path=ROOT/'provenance/FROZEN_EVALUATION_PROTOCOL_V1.json'
    assert frozen['group']==group and frozen['protocol_sha256']==sha(protocol_path)
    assert frozen['source_training_complete_sha256']==sha(run/'TRAINING_COMPLETE.json')
    queue=read(ROOT/'runs/EVALUATION_QUEUE.json')['stages'];proofs=[];roles=[]
    for model in frozen['models']:
        roles.extend(model['roles']);assert sha(ROOT/model['checkpoint']['path'])==model['checkpoint']['sha256']
        selected=[v for v in queue if v['kind']=='formal' and v['group']==group and v['id'].startswith(model['id']+'_')]
        assert len(selected)==3
        expected={('navtrain',tuple(range(5)),103288),('navtrain',tuple(range(5,10)),17475),('navtest',tuple(range(10)),12146)}
        observed=set()
        for entry in selected:
            stage=ROOT/entry['stage'];spec=read(stage/'SPECIFICATION.json');assert sha(stage/'SPECIFICATION.json')==entry['specification_sha256']
            assert not list((stage/'failures').glob('*.json')) and not list((stage/'audit/failures').glob('*.json'))
            accepted=read(stage/'AGENT_ACCEPTANCE.json');assert accepted['status']=='PASS_COMPLETE_AUDITED_STUDENT_EVALUATION'
            summary_path=ROOT/accepted['summary'];assert sha(summary_path)==accepted['summary_sha256'];summary=read(summary_path)
            assert summary['status']==accepted['status'] and summary['checkpoint_sha256']==model['checkpoint']['sha256']
            assert summary['training_config_sha256']==model['training_config_sha256'] and summary['model_id']==model['id']
            assert not summary['GT_used'] and not summary['test_used_for_model_selection'] and not summary['student_inference_requires_teacher_or_scoring']
            observed.add((summary['cohort'],tuple(summary['noises']),summary['cases']))
            for artifact in summary['artifacts'].values():assert sha(ROOT/artifact['path'])==artifact['sha256']
            proofs.append(dict(stage=entry['stage'],summary=accepted['summary'],sha256=accepted['summary_sha256']))
        assert observed==expected
    assert sorted(roles)==['primary_final','secondary_development_best']
    target=ROOT/'runs'/('GROUP_COMPUTE_COMPLETE_'+group+'.json');assert not target.exists()
    assigned=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['group']==group)
    proof=dict(status='PASS_ALL_FROZEN_STUDENT_COMPUTE_COMPLETE',time=stamp(),group=group,node=assigned['node'],job=assigned['job'],
        training_acceptance_sha256=sha(run/'TRAINING_AGENT_ACCEPTANCE.json'),frozen_models_sha256=sha(frozen_path),evaluations=proofs,
        unique_checkpoints=len(frozen['models']),return_retained_services_to_batch3=True,stop_or_release_DLC=False,
        original_Base_services_preserved=True,final_cross_group_analysis_and_report_still_required=True)
    atomic(target,proof);print(json.dumps({k:proof[k] for k in ['status','group','unique_checkpoints','return_retained_services_to_batch3','stop_or_release_DLC']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',required=True,choices=['H','T','HT']);main(p.parse_args())
