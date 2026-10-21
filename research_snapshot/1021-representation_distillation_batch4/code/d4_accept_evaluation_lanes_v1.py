"""Validate every retained evaluation lane before admitting full student tests."""
from d4_common_v2 import *
import argparse
from collections import Counter


def main(a):
    setup('evaluation_lane_acceptance/'+a.group,threads=2)
    import numpy as np
    from d4_evaluate_student_v1 import population
    assigned=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['group']==a.group)
    stage=ROOT/'runs/evaluation_engineering_v1'/a.group;spec=read(stage/'SPECIFICATION.json')
    assert (stage/'ALL_LANES_READY.json').exists() and not (stage/'AGENT_ACCEPTANCE.json').exists()
    assert not list((stage/'failures').glob('*.json'))
    assert (ROOT/'runs'/('distillation_main_v4_'+a.group)/'TRAINING_AGENT_ACCEPTANCE.json').exists()
    assert spec['task_template']['noises']==list(range(10))
    assert sha(spec['task_template']['checkpoint'])==spec['task_template']['checkpoint_sha256']
    assert sha(spec['task_template']['training_config'])==spec['task_template']['training_config_sha256']
    rows,prior,_=population('navtrain');golden={}
    for path in (ROOT/spec['golden_development_stage']).glob('rank*.json'):
        for record in read(path)['cases']:golden[record['global_index']]=record
    expected_count=len(spec['devices'])*spec['lanes_per_device'];paths=list((stage/'workers').glob('*/PASS.json'))
    assert len(paths)==expected_count
    counts=Counter();pids=set();sources=[];reference={}
    for path in sorted(paths):
        proof=read(path);assert proof['status']=='PASS_RETAINED_STUDENT_EVALUATION_LANE_EXACT'
        assert proof['old_five_scores_and_trajectories_exact'] and proof['new_five_Base_replay_check_exact'] and not proof['actual_test_used']
        worker=proof['worker'];assert worker['node']==assigned['node'] and worker['job']==assigned['job']
        assert worker['hostname'].startswith(assigned['job']+'-') and worker['device'] in spec['devices'] and worker['pid'] not in pids
        pids.add(worker['pid']);counts[worker['device']]+=1;assert len(proof['results'])==2
        for offset,result_ref in enumerate(proof['results']):
            result_path=Path(result_ref['path']);assert sha(result_path)==result_ref['sha256'];result=read(result_path);task=result['task']
            assert result['status']=='COMPLETE_STUDENT_EVALUATION_CHUNK' and task['engineering'] and task['valid_only_engineering']==bool(offset)
            assert task['cohort']=='navtrain' and task['noises']==list(range(10)) and task['indices']==spec['indices']
            for key in ['checkpoint_sha256','training_config_sha256','model_id']:assert task[key]==spec['task_template'][key]
            assert [v['global_index'] for v in result['cases']]==spec['indices']
            for case in result['cases']:
                record_path=ROOT/case['path'];assert sha(record_path)==case['sha256'];record=read(record_path);index=record['global_index']
                assert record['status']=='COMPLETE_STUDENT_NATIVE_EVALUATION' and record['token']==rows[index]['token'] and rows[index]['subset']=='validation'
                assert not record['GT_used'] and not record['student_inference_uses_teacher_or_PDMS']
                assert record['original_Base_S0_replayed_exactly_when_new_noises']
                assert record['interface']['same_actual_forward_for_all_student_trajectories']
                expected_scope='valid_tokens_only_for_test_diagnostic' if offset else 'full_context'
                assert record['interface']['teacher_comparison_scope']==expected_scope
                arrays=ROOT/record['arrays']['path'];assert sha(arrays)==record['arrays']['sha256']
                with np.load(arrays,allow_pickle=False) as z:
                    q=np.asarray(z['student_quality']);b=np.asarray(z['Base_quality']);t=np.asarray(z['student_trajectories']);bt=np.asarray(z['Base_trajectories'])
                    assert q.shape==b.shape==(10,7) and t.shape==bt.shape==(10,8,3) and z['noise_indices'].tolist()==list(range(10))
                    assert np.isfinite(q).all() and np.isfinite(b).all() and np.isfinite(t).all() and np.isfinite(bt).all()
                    assert np.array_equal(q[:5],np.asarray(golden[index]['quality'],dtype=np.float64))
                    assert np.array_equal(t[:5],np.asarray(golden[index]['trajectories'],dtype=np.float32))
                    assert np.array_equal(b[:5],prior['scores'][index,0]) and np.array_equal(bt[:5],prior['trajectories'][index,0])
                    for value in [q,b]:
                        assert (value>=0).all() and (value<=1+1e-8).all()
                        assert np.max(np.abs(value[:,1]*value[:,2]*(5*value[:,4]+5*value[:,3]+2*value[:,5])/12-value[:,0]))<1e-8
                    contents=(q.copy(),b.copy(),t.copy(),bt.copy(),record['interface']['sha256'])
                    if index in reference:
                        assert all(np.array_equal(x,y) for x,y in zip(contents[:4],reference[index][:4]))
                        assert contents[4]==reference[index][4]
                    else:reference[index]=contents
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),device=worker['device'],pid=worker['pid']))
    assert set(counts)==set(spec['devices']) and all(n==spec['lanes_per_device'] for n in counts.values())
    accepted=dict(status='PASS_ALL_RETAINED_STUDENT_EVALUATION_LANES',time=stamp(),group=a.group,node=assigned['node'],job=assigned['job'],
        physical_devices=len(counts),actual_model_lanes=len(paths),scenes_per_format=len(spec['indices']),formats=2,noises=list(range(10)),
        old_five_student_and_Base_exact_to_accepted_sources=True,new_five_and_interface_exact_across_all_lanes=True,
        actual_test_used=False,GT_used=False,original_Base_services_preserved=True,sources=sources,
        specification_sha256=sha(stage/'SPECIFICATION.json'),formal_student_evaluation_still_required=True)
    atomic(stage/'AGENT_ACCEPTANCE.json',accepted)
    print(json.dumps({k:v for k,v in accepted.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['H','T','HT'],required=True);main(p.parse_args())
