"""Actual VLM stage acceptance: seed-matched replay, 32 ranks and original-source scores."""
from common import *
import argparse,random,subprocess
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_global_refine_20261016_v5'

def audit32(stage):
    latest={};arms={a['id']:a for a in read(BASE/'stages'/stage/'arms.json')}
    for p in sorted((BASE/'receipts').glob(stage+'_a*.json')):
        r=read(p);latest[r['rank']]=p
    assert set(latest)==set(range(32)), 'The final stage must actually cover all 32 ranks'
    checks=[]
    for rank,p in latest.items():
        proof=read(p);path=BASE/'results'/p.name;assert sha(path)==proof['result_sha256'];doc=read(path)
        for v in doc['records']:
            assert v['seed']==seed(v['token'],v['seed_index']) and v['quality']==quality(v['score']['score'])
            assert np.asarray(v['trajectory']).shape==(8,3) and np.isfinite(v['trajectory']).all()
            assert all(np.isfinite(x) and 0<=x<=1+1e-8 for x in v['score'].values())
            assert v['edit']['relative_edit_max']<=arms.get(v['arm'],{}).get('cap',0)+1e-6
        checks.append(dict(rank=rank,path=str(path.relative_to(ROOT)),sha256=proof['result_sha256'],records=len(doc['records'])))
    return checks

def rescore(stage,dest):
    if (dest/'ACCEPTANCE.json').exists():return read(dest/'ACCEPTANCE.json')
    folder=BASE/'stages'/stage;rows={r['token']:r for r in read(folder/'panel.json')};cfg=read(ROOT/'configs/baseline.json')
    if not (dest/'request.json').exists():
        rng=random.Random(20261016);groups={k:[] for k in ['repair','damage','new_collision','collision_removed']};reservoir=[];count=0
        for path in sorted((BASE/'results').glob(stage+'_a*.json')):
            doc=read(path);assert doc['task']['stage']==stage
            # A VLM task contains several seeds. Comparisons must match BOTH.
            baselines={(r['token'],r['seed_index']):r for r in doc['records'] if r['arm']=='baseline'}
            for r in doc['records']:
                b=baselines[(r['token'],r['seed_index'])]['score'];v=r['score']
                if r['arm']!='baseline':
                    for kind,condition in [('repair',b['score']<.7 and v['score']>=.7),('damage',b['score']>.9 and v['score']<.7),('new_collision',b['no_at_fault_collisions']==1 and v['no_at_fault_collisions']<1),('collision_removed',b['no_at_fault_collisions']<1 and v['no_at_fault_collisions']==1)]:
                        if condition:groups[kind].append(r)
                count+=1
                if len(reservoir)<600:reservoir.append(r)
                else:
                    j=rng.randrange(count)
                    if j<600:reservoir[j]=r
        selected={};strata={}
        for kind,values in groups.items():
            rng.shuffle(values);strata[kind]=min(100,len(values))
            for r in values[:100]:selected[(r['token'],r['seed_index'],r['arm'])]=r
        rng.shuffle(reservoir)
        for r in reservoir:
            if len(selected)>=600:break
            selected[(r['token'],r['seed_index'],r['arm'])]=r
        assert len(selected)==600;expected=list(selected.values())
        tasks=[dict(token=r['token'],trajectory=r['trajectory'],metric_cache=rows[r['token']]['metric_cache'],metric_sha256=r['metric_sha256'],scoring=cfg['scoring']) for r in expected]
        atomic(dest/'expected.json',expected);atomic(dest/'STRATA.json',dict(sampled=strata,available={k:len(v) for k,v in groups.items()},same_token_and_seed_matched=True));atomic(dest/'request.json',tasks)
    if not (dest/'response.json').exists():
        subprocess.run([sys.executable,'-B',str(ROOT/'code/score.py'),str(dest/'request.json'),str(dest/'response.json'),'--original-source','/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive'],check=True,cwd=ROOT)
    expected=read(dest/'expected.json');actual=read(dest/'response.json');assert actual['status']=='PASS' and len(expected)==len(actual['results'])==600
    for a,b in zip(expected,actual['results']):assert a['token']==b['token'] and a['score']==b['score'] and a['quality']==b['quality']
    result=dict(status='PASS',time=stamp(),records=600,source=actual['import_source'],maximum_component_difference=0.,request_sha256=sha(dest/'request.json'),response_sha256=sha(dest/'response.json'),strata=read(dest/'STRATA.json'))
    atomic(dest/'ACCEPTANCE.json',result);return result

def replay():
    train=VOUT/'analysis/navtrain_locked';validation=VOUT/'analysis/validation_main';tr=read(train/'rows.json');vr=read(validation/'rows.json');index={r['token']:i for i,r in enumerate(tr)};idx=[index[r['token']] for r in vr]
    a=np.load(train/'scores.npy',mmap_mode='r');b=np.load(validation/'scores.npy',mmap_mode='r');ta=read(train/'arms.json');va=read(validation/'arms.json');vi={v['id']:i+1 for i,v in enumerate(va)}
    assert len(tr)==103288 and len(vr)==17475 and np.array_equal(a[:,idx,0,:],b[:,:,0,:])
    original=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r');oldrows=read(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/rows.json');assert [r['token'] for r in oldrows]==[r['token'] for r in tr] and np.array_equal(a[:,:,0,:],original[:,:,0,:])
    for i,arm in enumerate(ta,1):assert arm==va[vi[arm['id']]-1] and np.array_equal(a[:,idx,i,:],b[:,:,vi[arm['id']],:])
    return dict(status='PASS',training_cases=len(tr),validation_cases=len(vr),seeds=3,all_seven_fields_exact=True,arms=[v['id'] for v in ta],baseline_exact_previous_full_train=True,seedwise_validation_subset_exact=True)

def main(a):
    setup('vlm_repair/final_accept')
    semantic=a.study=='semantic';stage='final_test_semantic' if semantic else 'final_test';dest=SEM/'repair' if semantic else VOUT/'final'
    marker=dest/('INFERENCE_COMPLETE.json' if semantic else 'PRIMARY_INFERENCE_COMPLETE.json');assert read(marker)['status']=='PASS'
    assert read(dest/'ENGINEERING_PASS.json')['status']=='PASS';assert read(VOUT/'V6_EQUIVALENCE.json')['status']=='PASS'
    for p,h in read(VOUT/'REPAIR_EXECUTION_v6.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    checks=audit32(stage);rescore_result=rescore(stage,dest/'independent_rescore')
    scores=np.load(VOUT/'analysis'/stage/'scores.npy',mmap_mode='r');original=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r');assert np.array_equal(scores[:,:,0,:],original[:,:,0,:])
    summary=read(VOUT/'analysis'/stage/'SUMMARY.json');assert summary['coverage_exact'] and summary['protocol']['seeds']==[0,1,2,3,4]
    result=dict(status='PASS',time=stamp(),study=a.study,stage=stage,all_32_rank_checks=checks,rescore=rescore_result,score_sha256=sha(VOUT/'analysis'/stage/'scores.npy'),test_baseline_all_seven_fields_exact=True,test_distinct_records=summary['distinct_records'],
        primary_fulltrain_replay=None if semantic else replay(),full_subspace_grid_completion_not_implied=True,resource_release_not_a_success_condition=True)
    atomic(dest/'SCIENTIFIC_ACCEPTANCE.json',result);print('VLM_STAGE_SCIENTIFIC_ACCEPTANCE_PASS',a.study,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',choices=['primary','semantic'],required=True);main(p.parse_args())
