"""Replay an engineering checkpoint against saved validation outputs, no test."""
from d4_common_v2 import *
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import traceback


def main():
    setup('full_evaluation_smoke_v1');compatibility()
    import torch
    import numpy as np
    from vlm_intervene_v4 import Engine
    from d4_development_eval_v3 import initialize_score
    from d4_evaluate_student_v1 import run as evaluate,release_private_student
    assert torch.cuda.device_count()==1 and torch.cuda.mem_get_info()[0]>70*(1<<30)
    config=ROOT/'configs/training_engineering_v4/H.json';source=ROOT/'runs/training_engineering_v4_H'
    complete=read(source/'TRAINING_COMPLETE.json');checkpoint=complete['final_matched_exposure_checkpoint']
    expected={}
    for path in (source/'development/epoch02').glob('rank*.json'):
        for row in read(path)['cases']:expected[row['global_index']]=row
    indices=sorted(expected)[:2];engine=Engine();results=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=initialize_score) as pool:
        for valid_only in [False,True]:
            name='valid_format' if valid_only else 'full_context'
            task=dict(id='eval_smoke_'+name,output_stage='runs/student_eval_smoke_v1/'+name,indices=indices,cohort='navtrain',noises=list(range(10)),
                model_id='engineering_H_epoch2',checkpoint=str(ROOT/checkpoint['path']),checkpoint_sha256=checkpoint['sha256'],
                training_config=str(config),training_config_sha256=sha(config),engineering=True,valid_only_engineering=valid_only)
            result=evaluate(engine,task,pool)
            for case in read(result['path'])['cases']:
                record=read(ROOT/case['path']);old=expected[case['global_index']]
                with np.load(ROOT/record['arrays']['path'],allow_pickle=False) as z:
                    assert np.array_equal(z['student_trajectories'][:5],np.asarray(old['trajectories'],dtype=np.float32))
                    assert np.array_equal(z['student_quality'][:5],np.asarray(old['quality'],dtype=np.float64))
                assert record['original_Base_S0_replayed_exactly_when_new_noises']
            results.append(dict(task=task,result=result,old_five_predictions_and_scores_exact=True,Base_replay_exact=True))
    proof=dict(status='PASS_STUDENT_CHECKPOINT_NATIVE_FULL_AND_VALID_FORMAT_EVALUATION',time=stamp(),real_validation_scenes=2,
        execution_records=40,old_five_match_archived_training_development=True,new_five_student_and_Base_independently_scored=True,
        actual_test_used=False,GT_used=False,results=results,evaluator_sha256=sha(ROOT/'code/d4_evaluate_student_v1.py'))
    atomic(ROOT/'provenance/STUDENT_FULL_EVALUATION_SMOKE_V1.json',proof);release_private_student()
    print(json.dumps({k:proof[k] for k in ['status','real_validation_scenes','execution_records','actual_test_used']}),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'provenance/STUDENT_FULL_EVALUATION_SMOKE_FAILED_V1.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
