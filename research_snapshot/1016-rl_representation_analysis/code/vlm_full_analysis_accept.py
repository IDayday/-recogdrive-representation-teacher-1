"""Audit completed cross-validation geometry/results against actual cached inputs."""
from common import *
import argparse
import numpy as np
from vlm_core import VOUT
from vlm_scan import metadata
from vlm_space import METRICS
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    setup('vlm_repair/full_analysis_accept');assert all(len(list((VOUT/k/'receipts').glob('*.json')))==2272 for k in ['rapid','scan']);rows,q,exp,fold,sessions,high=metadata()
    assert len(rows)==103288 and int(exp.sum())==85813 and int((~exp).sum())==17475
    assert not set(sessions[exp])&set(sessions[~exp])
    for s in np.unique(sessions):assert len(np.unique(fold[sessions==s]))==1
    bad_old={b['name']+'__'+g for b in read(VOUT/'PIVOT_PLAN.json')['blocks'] if b['name'].startswith(('language','interface')) for g in ['command','requirements']}
    assert len(bad_old)==64
    checks=[];mom_checks=[]
    for kind in ['rapid','scan']:
        base=VOUT/kind;cfg=read(base/'CONFIGS.json');complete=sorted((base/'receipts').glob('*.json'))
        for receipt in complete:
            proof=read(receipt);path=base/'results'/receipt.name;assert sha(path)==proof['result_sha256'];r=read(path)
            source=read(VOUT/'cells'/(r['cell']+'.json'));assert r['source_sha256']==source['sha256']
            if r['status']=='INELIGIBLE':
                assert r['cell'] in bad_old or r['valid_cases']<103288
                checks.append(dict(kind=kind,cell=r['cell'],status=r['status']));continue
            assert r['status']=='COMPLETE' and not r['test_accessed'] and not r['heldout_validation_evaluated']
            assert r['metric_fields']==METRICS and sha(ROOT/r['array_path'])==r['array_sha256']
            with np.load(ROOT/r['array_path']) as z:
                m=z['metrics'];status=z['status'];ranks=z['ranks'];idx=z['evaluation_indices']
                assert m.shape==(2,6,len(cfg),len(METRICS)) and status.shape==(2,5,len(cfg))
                assert (exp[idx]).all() and ((q[idx]<.7)|(q[idx]>.9)).all() and int((q[idx]>.9).sum())<=8192
                assert np.array_equal(z['fold_ids'],fold[idx]) and len(np.unique(idx))==len(idx)
                for k in [0,1,4,6,8]:
                    v=m[:,:,:,k];v=v[np.isfinite(v)];assert ((v>=-1e-10)&(v<=1+1e-10)).all()
                eligible=(status==0).all(1)
                assert not np.isfinite(m[:,5,:,0][~eligible]).any()
                residual=np.array([c['kind'].endswith('residual') for c in cfg])
                ks=np.array([c.get('ks') or 0 for c in cfg]);kf=np.array([c.get('kf') or 0 for c in cfg]);rr=np.array([c.get('r') or 0 for c in cfg])
                use=(status==0)&residual[None,None,:]
                for field,request in [(0,ks),(1,kf),(2,rr)]:assert (ranks[...,field][use]>=np.broadcast_to(request,ranks.shape[:-1])[use]).all()
                bounds=np.minimum(kf,np.maximum(0,r['dimension']-ks))
                assert not ((ranks[...,2]>bounds[None,None,:])&residual[None,None,:]).any()
            checks.append(dict(kind=kind,cell=r['cell'],status=r['status'],eligible=[int(x) for x in eligible.sum(1)],evaluation_cases=len(idx)))
            # Finite-coordinate sufficient-statistics check in a deterministic
            # subset. The original cache whole-SHA audit already covers all bytes.
            if len(mom_checks)<a.moment_cells and r['cell'] not in {x['cell'] for x in mom_checks}:
                assert sha(ROOT/r['moment_path'])==r['moment_sha256']
                x=np.load(ROOT/source['path'],mmap_mode='r');cols=np.unique(np.linspace(0,x.shape[1]-1,8,dtype=int));valid=np.isfinite(x[:,0]);fit=exp&valid
                with np.load(ROOT/r['moment_path']) as z:
                    for suffix,mask in [('s',q>.9),('f',q<.7)]:
                        v=np.asarray(x[fit&mask][:,cols],dtype=np.float64);n=int(z['n'+suffix]);assert len(v)==n
                        assert np.allclose(v.sum(0),z['s'+suffix][cols],rtol=1e-10,atol=1e-7)
                        assert np.allclose(v.T@v,z['g'+suffix][np.ix_(cols,cols)],rtol=1e-10,atol=1e-6)
                mom_checks.append(dict(cell=r['cell'],columns=cols.tolist(),full_class_rows=True))
    output=VOUT/'audits'/('analysis_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(output,dict(status='PASS',time=stamp(),completed_results=checks,moment_checks=mom_checks,
        session_splits_disjoint=True,case_seed_and_fold_identity=True,rank_constraints_and_metrics_checked=True,
        invalid_old_semantic_cells_excluded=True,all_4544_original_results_committed=True,coverage_is_snapshot_not_full_grid_completion=False,probability_fields=[0,1,4,6,8]))
    assert len(checks)==4544
    atomic(VOUT/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json',dict(path=str(output.relative_to(ROOT)),sha256=sha(output),status='PASS'))
    print(json.dumps(dict(status='PASS',results=len(checks),moment_cells=len(mom_checks),path=str(output.relative_to(ROOT)))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--moment-cells',type=int,default=6);main(p.parse_args())
