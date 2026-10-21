"""Audit real sparse inference and independently rescore composed policy paths."""
from common import *
import random,subprocess
import numpy as np
from vlm_core import VOUT
from vlm_scan import metadata
from vlm_obs_qda_gate import OUT,ungated
from vlm_obs_gate_test import STAGE,BASE
from vlm_final_accept import audit32
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/obs_gate_accept');compatibility()
    assert read(OUT/'INFERENCE_COMPLETE.json')['status']=='PASS'
    assert read(OUT/'FEATURE_ENGINEERING_PASS.json')['status']=='PASS'
    for name in ['PREPARE','COLLECT','TEST']:
        for p,h in read(VOUT/f'OBS_QDA_GATE_{name}_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    checks=audit32(STAGE);locked=read(OUT/'FINAL_LOCK.json');testlock=read(OUT/'TEST_LOCK.json')
    assert testlock['source_actual_policy_lock_sha256']==sha(OUT/'FINAL_LOCK.json')
    for role in locked['roles'].values():assert ungated(role['parent'])
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');positions={r['token']:i for i,r in enumerate(rows)}
    folder=VOUT/'analysis/final_test_obs_qda_gate';scores=np.load(folder/'scores.npy',mmap_mode='r');edits=np.load(folder/'edits.npy',mmap_mode='r')
    old=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r');base=np.asarray(old[:,:,0,:]);assert np.array_equal(scores[:,:,0,:],base)
    virtual=read(folder/'arms.json');roles={r['id']:r for r in locked['roles'].values()}
    marker=read(OUT/'TEST_MASKS_READY.json');assert sha(ROOT/marker['path'])==marker['sha256']
    with np.load(ROOT/marker['path']) as z:
        masks={a['id']:np.array(z[a['id']]) for a in virtual}
        for a in virtual:
            risk=z[a['id']+'__risk'];g=roles[a['id']]['gate']
            assert np.array_equal(masks[a['id']],np.isfinite(risk)&(risk>g['threshold']))
    _,q,exp,_,_,_=metadata()
    source=read(OUT/'RISKS_READY.json');assert sha(ROOT/source['path'])==source['sha256']
    with np.load(ROOT/source['path']) as z:
        for r in roles.values():
            g=r['gate'];assert float(np.quantile(z['risk'][exp&(q>.9),g['column']],g['quantile']))==g['threshold']
    reference=VOUT/'final/original_base_trajectories.npz';proof=read(reference.with_suffix('.json'))
    assert sha(reference)==proof['array_sha256'] and proof['rows_sha256']==digest(rows)
    with np.load(reference) as z:base_paths=np.array(z['trajectories'])
    records={};raw_sources=[]
    for p in sorted((BASE/'results').glob(STAGE+'_a*.json')):
        receipt=read(BASE/'receipts'/p.name);assert sha(p)==receipt['result_sha256'];doc=read(p)
        for r in doc['records']:
            key=(r['seed_index'],positions[r['token']],r['arm']);assert key not in records;records[key]=r
            if r['arm']=='baseline':
                assert np.array_equal(np.asarray(r['trajectory'],dtype=np.float64),base_paths[key[0],key[1]])
                assert np.array_equal([r['score'][f] for f in ['score',*COMPONENTS]],base[key[0],key[1]])
        raw_sources.append(dict(path=str(p.relative_to(ROOT)),sha256=receipt['result_sha256']))
    actual_arms=read(VOUT/'analysis'/STAGE/'arms.json')
    actual_rows=read(VOUT/'analysis'/STAGE/'rows.json');subset={positions[r['token']] for r in actual_rows}
    assert set(np.flatnonzero((base[:,:,0]<.7).any(0))).issubset(subset)
    for col,a in enumerate(virtual,1):
        assert set(np.flatnonzero(masks[a['id']])).issubset(subset)
        for j in range(5):
            assert np.array_equal(scores[j,~masks[a['id']],col,:],base[j,~masks[a['id']],:])
            assert not edits[j,~masks[a['id']],col,:].any()
        for i in np.flatnonzero(masks[a['id']]):
            for j in range(5):
                r=records[j,int(i),a['underlying_arm_id']]
                assert np.array_equal(scores[j,i,col,:],[r['score'][f] for f in ['score',*COMPONENTS]])
    dest=OUT/'independent_rescore';dest.mkdir(exist_ok=True)
    if not (dest/'request.json').exists():
        rng=random.Random(20261017);available=[(j,i,col) for j in range(5) for i in range(len(rows)) for col in range(1,len(virtual)+1)]
        chosen={};strata={}
        for label in ['repair','damage','new_collision','collision_removed']:
            values=[]
            for key in available:
                j,i,c=key;b=base[j,i];v=scores[j,i,c]
                good={'repair':b[0]<.7 and v[0]>=.7,'damage':b[0]>.9 and v[0]<.7,
                      'new_collision':b[1]==1 and v[1]<1,'collision_removed':b[1]<1 and v[1]==1}[label]
                if good:values.append(key)
            rng.shuffle(values);strata[label]=dict(available=len(values),sampled=min(100,len(values)))
            for key in values[:100]:chosen[key]=True
        rng.shuffle(available)
        for key in available:
            if len(chosen)==600:break
            chosen[key]=True
        assert len(chosen)==600;expected=[];requests=[];scoring=read(ROOT/'configs/baseline.json')['scoring']
        for j,i,col in chosen:
            a=virtual[col-1]
            trajectory=records[j,i,a['underlying_arm_id']]['trajectory'] if masks[a['id']][i] else base_paths[j,i].tolist()
            score={f:float(v) for f,v in zip(['score',*COMPONENTS],scores[j,i,col])}
            expected.append(dict(token=rows[i]['token'],seed_index=j,arm=a['id'],score=score,quality=quality(score['score'])))
            requests.append(dict(token=rows[i]['token'],trajectory=trajectory,metric_cache=rows[i]['metric_cache'],
                metric_sha256=rows[i]['metric_sha256'],scoring=scoring))
        atomic(dest/'expected.json',expected);atomic(dest/'request.json',requests);atomic(dest/'STRATA.json',strata)
    if not (dest/'response.json').exists():
        subprocess.run([sys.executable,'-B',str(ROOT/'code/score.py'),str(dest/'request.json'),str(dest/'response.json'),
            '--original-source','/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive'],cwd=ROOT,check=True)
    expected=read(dest/'expected.json');actual=read(dest/'response.json');assert actual['status']=='PASS' and len(expected)==len(actual['results'])==600
    for a,b in zip(expected,actual['results']):assert a['token']==b['token'] and a['score']==b['score'] and a['quality']==b['quality']
    failure=read(OUT/'ungated/ACCEPTANCE.json');assert sha(ROOT/failure['score_path'])==failure['scores_sha256']
    result=dict(status='PASS',time=stamp(),all_32_real_union_rank_checks=checks,raw_sources=raw_sources,
        real_union_baseline_all_coordinates_exact=True,composed_baseline_all_seven_fields_exact=True,
        risk_masks_only_from_observations_and_frozen_thresholds=True,all_false_positive_outputs_really_computed=True,
        actual_parent_Base_failures_all_five_seeds_covered=True,independent_rescore_records=600,
        maximum_rescore_difference=0.,scores_sha256=sha(folder/'scores.npy'),
        test_lock_sha256=sha(OUT/'TEST_LOCK.json'),request_sha256=sha(dest/'request.json'),response_sha256=sha(dest/'response.json'),
        scope='Observation-only gated real trajectories; no invented unconditional parent values for uncomputed nonfailures.')
    atomic(OUT/'SCIENTIFIC_ACCEPTANCE.json',result);print('OBSERVATION_QDA_GATE_SCIENTIFIC_ACCEPTANCE_PASS',flush=True)


if __name__=='__main__':main()
