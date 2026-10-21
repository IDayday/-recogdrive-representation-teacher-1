"""One explicitly authorized first42 teacher snapshot, never on live-best updates."""
from r3_common import *
import argparse


def main(a):
    import numpy as np
    train_path=ROOT/'analysis'/a.train_stage/'SUMMARY.json';test_path=ROOT/'analysis'/a.test_stage/'SUMMARY.json'
    train=read(train_path);test=read(test_path);assert train['status']==test['status']=='PASS_COMPLETE_AUDITED_FIRST42'
    assert train['cohort']=='navtrain' and train['cases']==103288 and test['cohort']=='navtest' and test['cases']==12146
    assert train['pack_sha256']==test['pack_sha256']==sha(ROOT/'manifests/first42_v1.json')
    output=ROOT/'teachers/first42_v1';assert not output.exists();output.mkdir(parents=True)
    pack=read(ROOT/'manifests/first42_v1.json');atomic(output/'PACK.json',pack);ids=[e['id'] for e in pack['entries']]
    index_path=ROOT/train['artifacts']['CASE_INDEX.json']['path'];assert sha(index_path)==train['artifacts']['CASE_INDEX.json']['sha256'];cases=read(index_path)
    selected_path=ROOT/train['artifacts']['selected.npy']['path'];assert sha(selected_path)==train['artifacts']['selected.npy']['sha256'];selected=np.load(selected_path,mmap_mode='r')
    rows=read(train['rows']);assert sha(train['rows'])==train['rows_sha256'] and len(cases)==len(rows)==103288
    streams={name:(output/(name+'.jsonl')).open('x') for name in ['R1','R2','R3']};counts={name:0 for name in streams};splits={}
    try:
        for ref in cases:
            i=ref['global_index'];row=rows[i];assert ref['token']==row['token'];choices=selected[i]
            common=dict(token=row['token'],session=row['session'],subset=row['subset'],cohort='navtrain',global_index=i,
                        source_rows=train['rows'],source_rows_sha256=train['rows_sha256'],record=ref['path'],record_sha256=ref['sha256'],
                        interfaces=str((Path(ref['path']).parent/'teacher_interfaces.npz')),interfaces_sha256=ref['interfaces_sha256'],
                        interface_position='action_head.feature_encoder output after actual intervention; full valid tokens',dtype='float32',
                        trajectory_and_interface_same_actual_execution_audited=True,noise_indices=[0,1,2,3,4],
                        training_permission='Preserve split; validation is not automatically student-training data')
            selections=dict(R1=[ids[int(c)] for c in choices[:5]],R2=[ids[int(choices[5])]]*5,R3=[ids[int(choices[6])]]*5)
            for endpoint,targets in selections.items():
                record=dict(common,endpoint=endpoint,candidate_ids_by_noise=targets,
                            target_lookup='Read matching arm/seed in source records; interface array key equals that actual record interface_sha256')
                if endpoint=='R3':record.update(selection_noise_indices=[0,1,2],evaluation_noise_indices=[3,4],teacher_targets_include_selection_and_evaluation_noise=True)
                streams[endpoint].write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');counts[endpoint]+=1
            splits[row['subset']]=splits.get(row['subset'],0)+1
    finally:
        for stream in streams.values():stream.close()
    assert counts==dict(R1=103288,R2=103288,R3=103288) and splits==dict(exploration=85813,validation=17475)
    artifacts={name:dict(path=str((output/(name+'.jsonl')).relative_to(ROOT)),sha256=sha(output/(name+'.jsonl')),scenes=counts[name],targets=counts[name]*5) for name in streams}
    freeze=dict(status='FROZEN_FIRST42_TEACHER_SNAPSHOT',time=stamp(),candidate_entries=42,pack_sha256=sha(output/'PACK.json'),source_pack_sha256=train['pack_sha256'],
                train_summary=str(train_path.relative_to(ROOT)),train_summary_sha256=sha(train_path),test_reference_summary=str(test_path.relative_to(ROOT)),test_reference_summary_sha256=sha(test_path),
                splits=splits,artifacts=artifacts,physical_arrays='Immutable first42 run outputs; no duplicate multi-terabyte copy',
                test_targets_included_for_student_training=False,R3_report_evaluates_S3S4_only=True,
                later_live_best_updates_do_not_change_this_snapshot=True,new_teacher_snapshot_requires_explicit_user_request=True,
                all_sources_and_actual_execution_assets_preserved=True)
    atomic(output/'FROZEN.json',freeze);atomic(ROOT/'provenance/FIRST42_TEACHER_FROZEN.json',dict(status=freeze['status'],time=stamp(),path=str((output/'FROZEN.json').relative_to(ROOT)),sha256=sha(output/'FROZEN.json')))
    print(json.dumps(dict(status=freeze['status'],splits=splits,endpoint_scene_counts=counts)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--train-stage',default='first42_navtrain_v1');p.add_argument('--test-stage',default='first42_navtest_v1');main(p.parse_args())
