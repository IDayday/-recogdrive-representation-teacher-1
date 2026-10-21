"""Observation-only quadratic gates, calibrated on existing exploration features."""
from common import *
import numpy as np
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_scan import metadata,save_npz
from repair_queue_v2 import atomic_unique as atomic

OUT=VOUT/'observation_qda_gate'


def definitions():
    values=[s['fit'] for s in read(VOUT/'qda_controls/PROTOCOL.json')['sites']]
    for spec in read(VOUT/'late_token_coverage/QDA_SELECTION_LOCK.json')['selected']:
        values.append(read(VOUT/'late_token_coverage/fits'/(digest(spec)[:20]+'.json'))['fit'])
    assert len(values)==20 and len({(f['cell'],f['r'],f['centering']) for f in values})==20
    return sorted(values,key=lambda f:(f['cell'],f['r']))


def quadratic(x,fit):
    # The determinant offset is constant within a fitted gate and its
    # high-quality quantile, so it cancels in every threshold comparison.
    with np.load(ROOT/fit['path']) as z:
        b=np.asarray(z['basis'],dtype=np.float64);c=np.asarray(z['center'],dtype=np.float64)
        mh=np.asarray(z['mh'],dtype=np.float64);mf=np.asarray(z['mf'],dtype=np.float64)
        ci=np.asarray(z['cov_inv_s'],dtype=np.float64);fi=np.asarray(z['cov_inv_f'],dtype=np.float64)
    assert ci.shape==fi.shape==(fit['r'],fit['r'])
    result=np.full(len(x),np.nan)
    for begin in range(0,len(x),256):
        a=np.asarray(x[begin:begin+256],dtype=np.float64);valid=np.isfinite(a).all(1)
        p=(a[valid]-c)@b;ds=p-mh;df=p-mf
        v=np.full(len(a),np.nan);v[valid]=.5*((ds*(ds@ci)).sum(1)-(df*(df@fi)).sum(1))
        result[begin:begin+len(a)]=v
    return result


def risk_table():
    marker=OUT/'RISKS_READY.json'
    if marker.exists():
        r=read(marker);assert sha(ROOT/r['path'])==r['sha256'];return r
    rows,q,exp,fold,sessions,high=metadata();scores=[];gates=[];proofs=[]
    for fit in definitions():
        assert sha(ROOT/fit['path'])==fit['sha256']
        proof=read(ROOT/fit['cell_proof_path']);x=np.load(ROOT/proof['path'],mmap_mode='r')
        assert len(x)==103288 and proof['valid_cases']==103288
        with threadpool_limits(2):risk=quadratic(x,fit)
        assert np.isfinite(risk).all();scores.append(risk)
        for quantile in read(VOUT/'OBS_QDA_GATE_PROTOCOL.json')['quantiles']:
            threshold=float(np.quantile(risk[exp&(q>.9)],quantile))
            gate=dict(fit=fit,quantile=quantile,threshold=threshold,missing='retain_base')
            gate['id']='qda_risk_'+digest(gate)[:20];gate['column']=len(scores)-1;gates.append(gate)
        proofs.append(dict(cell=fit['cell'],r=fit['r'],fit_sha256=fit['sha256'],source_sha256=proof['sha256']))
    path=OUT/'training_risks.npz';h=save_npz(path,risk=np.column_stack(scores))
    result=dict(status='PASS',time=stamp(),path=str(path.relative_to(ROOT)),sha256=h,gates=gates,
        fits=proofs,cases=len(rows),gates_count=len(gates),calibration='exploration S0 >90 only',
        no_validation_labels_for_calibration=True,no_test_access=True)
    atomic(marker,result);return result


def ungated(a):
    return all(ungated(p) for p in a['parts']) if a['method']=='combination' else a.get('gate','none')=='none'


def select():
    lock=OUT/'FINAL_LOCK.json'
    if lock.exists():return read(lock)
    table=risk_table();folder=VOUT/'analysis/validation_main'
    summary=read(folder/'SUMMARY.json');assert summary['coverage_exact'] and summary['protocol']['seeds']==[0,1,2]
    rows=read(folder/'rows.json');assert len(rows)==17475
    indices=[r['global_index'] for r in rows]
    with np.load(ROOT/table['path']) as z:risk=np.array(z['risk'][indices])
    gates=table['gates'];mask=np.array([risk[:,g['column']]>g['threshold'] for g in gates])
    scores=np.load(folder/'scores.npy',mmap_mode='r');edits=np.load(folder/'edits.npy',mmap_mode='r')
    arms=read(folder/'arms.json');parents=[(i+1,a) for i,a in enumerate(arms) if ungated(a)]
    assert len(parents)<=128;baseline=np.asarray(scores[:,:,0,:]);n=baseline.shape[0]*baseline.shape[1]
    records=[]
    for index,parent in parents:
        value=np.asarray(scores[:,:,index,:]);change=(edits[:,:,index,3]>1e-8).sum(0)
        delta=(value[:,:,0]-baseline[:,:,0]).sum(0);changes=mask.astype('int64')@change
        means=(mask@delta)/n*100
        metrics={}
        for label,field,threshold in [('collision_net',1,1-1e-7),('offroad_net',2,1-1e-7),('ttc_net',4,1-1e-7),('failure_net',0,.7)]:
            difference=((value[:,:,field]<threshold).astype('int64')-(baseline[:,:,field]<threshold).astype('int64')).sum(0)
            metrics[label]=mask.astype('int64')@difference
        difference=((value[:,:,0]<=1e-10).astype('int64')-(baseline[:,:,0]<=1e-10).astype('int64')).sum(0)
        metrics['zero_net']=mask.astype('int64')@difference
        for j,gate in enumerate(gates):
            if not changes[j]:continue
            identity='obs_qda_'+digest(dict(parent=parent,gate=gate['id']))[:20]
            r=dict(id=identity,parent=parent,gate=gate,mean_delta_pdms=float(means[j]),
                changed_outputs=int(changes[j]),risk_positive_cases=int(mask[j].sum()),
                **{key:int(v[j]) for key,v in metrics.items()})
            r['safe_net']=r['mean_delta_pdms']>=0 and all(r[k]<=0 for k in ['collision_net','offroad_net','zero_net'])
            records.append(r)
    atomic(OUT/'VALIDATION_SEARCH.json',dict(status='COMPLETE',time=stamp(),parents=len(parents),gate_rules=len(gates),
        requested_combinations=len(parents)*len(gates),active_records=records,cases=len(rows),seeds=3,
        score_sha256=sha(folder/'scores.npy'),risk_sha256=table['sha256'],whole_trajectory_selection=True))
    if not records:
        result=dict(status='COMPLETE',time=stamp(),reason='No active quadratic-gated validation candidate.',no_positive_claim=True)
        atomic(OUT/'NO_COMPETITIVE_CANDIDATES.json',result);return result
    safe=[r for r in records if r['safe_net']]
    roles=dict(pdms_priority=max(records,key=lambda r:r['mean_delta_pdms']),
        safety_priority=max(safe,key=lambda r:r['mean_delta_pdms']) if safe else min(records,key=lambda r:(sum(max(r[k],0) for k in ['collision_net','offroad_net','zero_net']),-r['mean_delta_pdms'])))
    result=dict(status='FROZEN_BEFORE_OWN_TEST_FEATURE_EXTRACTION',time=stamp(),roles=roles,
        safety_eligible=bool(safe),safety_fallback_diagnostic_only=not bool(safe),
        source_validation_sha256=sha(OUT/'VALIDATION_SEARCH.json'),source_risks_sha256=table['sha256'],
        test_accessed=False,neural_model_and_operators_unchanged=True)
    atomic(lock,result);return result


if __name__=='__main__':
    setup('vlm_repair/observation_qda_gate');OUT.mkdir(exist_ok=True);risk_table()
    folder=VOUT/'analysis/validation_main'
    while not (folder/'SUMMARY.json').exists():time.sleep(30)
    r=select();print('OBSERVATION_QDA_GATE_SELECTION',r['status'],flush=True)
