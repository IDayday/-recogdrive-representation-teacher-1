"""Assemble independent CPU proofs for the complete fixed-R2 input augmentation."""
from d4_common import *


def main():
    import numpy as np
    stage=ROOT/'runs/full_context_replay_v1';config=read(ROOT/'configs/REPLAY_SERVICE_V1.json')
    assert not (stage/'AGENT_ACCEPTANCE.json').exists()
    assert not list((stage/'failures').glob('*.json')) and not list((stage/'audit/failures').glob('*.json'))
    expected=(config['case_count']+config['chunk_size']-1)//config['chunk_size'];receipts=list((stage/'receipts').glob('*.json'))
    assert len(receipts)==expected and len(list((stage/'audit/shards').glob('*.json')))==expected
    seen=np.zeros(config['case_count'],dtype=bool);sources=[];cases=[]
    for receipt_path in sorted(receipts):
        proof_path=stage/'audit/shards'/receipt_path.name;proof=read(proof_path)
        assert proof['status']=='PASS_INDEPENDENT_FULL_CONTEXT_CPU_AUDIT' and proof['receipt_sha256']==sha(receipt_path)
        receipt=read(receipt_path);assert receipt['task']['scenes_sha256']==config['task_template']['scenes_sha256']
        assert [c['global_index'] for c in proof['cases']]==receipt['task']['indices']
        for case in proof['cases']:
            i=case['global_index'];assert 0<=i<len(seen) and not seen[i];seen[i]=True
            cases.append(dict(case,path=str((stage/'cases'/case['token']/'RESULT.json').relative_to(ROOT))))
        sources.append(dict(path=str(proof_path.relative_to(ROOT)),sha256=sha(proof_path)))
    assert seen.all()
    scenes=read(config['task_template']['scenes']);assert all(scenes[c['global_index']]['token']==c['token'] for c in cases)
    target=ROOT/'analysis/full_context_replay_v1';atomic(target/'CASE_INDEX.json',sorted(cases,key=lambda c:c['global_index']))
    intake=read(ROOT/'provenance/SOURCE_INTAKE_V1.json');frozen=B3/'teachers/first42_v1/FROZEN.json'
    assert sha(frozen)==intake['frozen_snapshot_sha256']
    proof=dict(status='PASS_COMPLETE_INDEPENDENTLY_AUDITED_FIXED_R2_FULL_CONTEXT',time=stamp(),cases=len(cases),chunks=expected,
        actual_five_noise_outputs=len(cases)*5,teacher_candidates_reselected=False,GT_used=False,
        original_first42_snapshot_sha256=sha(frozen),configuration_sha256=sha(ROOT/'configs/REPLAY_SERVICE_V1.json'),
        case_index=dict(path=str((target/'CASE_INDEX.json').relative_to(ROOT)),sha256=sha(target/'CASE_INDEX.json')),
        full_context_includes_original_padding=True,all_old_valid_interfaces_and_all_five_trajectories_and_fresh_scores_exact=True,
        proof_shards=sources,not_a_new_teacher_selection_snapshot=True,source_classification_for_training='manifests/R2_TRAINING_SCENES_V2.json')
    atomic(target/'SUMMARY.json',proof);atomic(stage/'AGENT_ACCEPTANCE.json',dict(status=proof['status'],time=stamp(),summary=str((target/'SUMMARY.json').relative_to(ROOT)),summary_sha256=sha(target/'SUMMARY.json')))
    print(json.dumps({k:proof[k] for k in ['status','cases','chunks','actual_five_noise_outputs','GT_used']}),flush=True)


if __name__=='__main__':main()
