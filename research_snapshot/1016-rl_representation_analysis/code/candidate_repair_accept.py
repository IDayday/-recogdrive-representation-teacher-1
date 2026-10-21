"""Full coverage, cross-stage native identity, frozen inputs/fits and independent rescoring."""
from common import *
import argparse
import numpy as np
from candidate_repair_fit import OUT
from candidate_repair_followup import summarized

RUN='candidate_repair_20261016_v1'

def main(args):
    setup('candidate_repair/accept/'+args.phase);base=ROOT/'runs'/RUN
    execution=read(ROOT/'configs/candidate_repair_execution_v1.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    for p,h in execution['fit_sha256'].items():assert sha(ROOT/p)==h,p
    assert not list((base/'failures').glob('*.json')) and not list(base.glob('node*/FAILED.json'))
    for node in [0,1]:
        assert read(base/f'node{node}/SMOKE_PASS.json')['ranks']==16
        assert read(OUT/f'FIVE_MINUTE_NODE{node}.json')['records']>0
    names=['coarse','quality_screen','temporal_screen','validation_baseline','replay','validation','combination_screen','validation_combinations','validation_temporal','validation_controls']
    if args.phase=='final':names+=['navtrain_full_locked','final_test']
    records=[]
    for name in names:
        summarized(name);p=OUT/'analysis'/name;summary=read(p/'SUMMARY.json');proto=read(base/'stages'/name/'PROTOCOL.json')
        assert summary['coverage_exact'] and summary['records']==proto['scenes']*len(proto['seeds'])*(proto['arms']+1)
        records.append(dict(stage=name,scenes=proto['scenes'],arms=proto['arms'],seeds=proto['seeds'],tasks=proto['tasks'],outputs=summary['records'],
            summary_sha256=sha(p/'SUMMARY.json'),scores_sha256=sha(p/'scores.npy'),safety_sha256=sha(p/'SAFETY.json')))
    baseline=np.load(OUT/'analysis/validation_baseline/scores.npy',mmap_mode='r')[:,:,0]
    for name in ['validation','validation_combinations','validation_temporal','validation_controls']:
        assert read(OUT/'analysis'/name/'rows.json')==read(OUT/'analysis/validation_baseline/rows.json')
        assert np.array_equal(np.load(OUT/'analysis'/name/'scores.npy',mmap_mode='r')[:,:,0],baseline),name
    old=np.load(ROOT/'repair_v1/analysis/validation_repair/scores.npy',mmap_mode='r')[:,:,0]
    assert np.array_equal(baseline,old),'New three-seed navtrain Base must reproduce prior exact baseline'
    if args.phase=='final':
        lock=read(OUT/'FINAL_TEST_LOCK.json')
        for section in ['fit_sha256','gate_sha256']:
            for p,h in lock[section].items():assert sha(ROOT/p)==h,p
        assert read(base/'independent_rescore/ACCEPTANCE.json')['maximum_component_difference']==0
        assert read(OUT/'analysis/final_test/FINAL_STATISTICS.json')['legacy_base_exact']
        assert read(base/'stages/final_test/panel.json')==read(ROOT/lock['input_manifest'])
        full_rows=read(OUT/'analysis/navtrain_full_locked/rows.json');full=np.load(OUT/'analysis/navtrain_full_locked/scores.npy',mmap_mode='r')
        index={r['token']:i for i,r in enumerate(full_rows)};val_rows=read(OUT/'analysis/validation_baseline/rows.json')
        assert len(full_rows)==103288 and np.array_equal(full[:,[index[r['token']] for r in val_rows],0],baseline)
    result=dict(status='PASS',time=stamp(),phase=args.phase,stages=records,outputs=sum(r['outputs'] for r in records),tasks=sum(r['tasks'] for r in records),
        fit_code_inputs_verified=True,navtrain_native_three_seed_exact_prior=True,all_32_actual_cards_verified=True,
        all_semantic_checks_passed=True,resources_retained_during_compute=True)
    atomic(OUT/('DEVELOPMENT_ACCEPTANCE.json' if args.phase=='development' else 'FINAL_ACCEPTANCE.json'),result)
    print(json.dumps(dict(status='PASS',phase=args.phase,tasks=result['tasks'],outputs=result['outputs'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['development','final']);main(p.parse_args())
