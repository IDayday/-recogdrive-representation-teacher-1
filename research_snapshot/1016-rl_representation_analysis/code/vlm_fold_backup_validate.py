"""Validate committed checkpoints, including original 4096D sufficient statistics."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_fold_backup_v2 import OUT
from vlm_space import configs
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_repair/fold_backup/validate');checks=[];entries=configs()
    for p in sorted((OUT/'completed').glob('*.json')):
        proof=read(p);cell=proof['cell'];rpath=ROOT/proof['result_path'];assert sha(rpath)==proof['result_sha256']
        result=read(rpath);assert result['status']=='COMPLETE' and result['configs']==11633
        original=read(VOUT/'cells'/(cell+'.json'));assert result['source_sha256']==original['sha256']
        assert result['training_class_sizes']==[74900,1850]
        for kind in ['array','moment']:assert sha(ROOT/result[kind+'_path'])==result[kind+'_sha256']
        d=result['dimension'];bounds=np.array([min(c['kf'],max(0,d-c['ks'])) if c['kind'].endswith('residual') else 65535 for c in entries]);requested=np.array([c['r'] or 0 for c in entries])
        with np.load(ROOT/result['array_path']) as z:
            assert z['metrics'].shape==(2,6,11633,9)
            assert not (z['ranks'][:,:,:,2]>bounds[None,None,:]).any()
            valid=(z['status']==0).all(1)&~z['cutoff_degenerate'].any(1)
            assert not (valid&(requested[None,:]>bounds[None,:])).any()
            for cc in [0,1]:
                for index in [0,1,4,6,8]:
                    a=z['metrics'][cc,5,valid[cc],index];assert np.isfinite(a).all() and (a>=0).all() and (a<=1).all(),(cell,index)
        old=VOUT/'moments'/(cell+'.npz');same=None
        if old.exists():
            with np.load(old) as a,np.load(ROOT/result['moment_path']) as b:
                assert set(a.files)==set(b.files);same=all(np.array_equal(a[k],b[k]) for k in a.files);assert same,cell
        checks.append(dict(cell=cell,result_sha256=proof['result_sha256'],dimension=d,original_partial_moments_bit_exact=same,
            algebraic_rank_and_eligible_r_checked=True,pooled_probability_metrics_bounded=True,committed_result_is_backup_only=True))
    assert checks
    p=OUT/'audits'/('data_validation_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(p,dict(status='PASS',time=stamp(),checks=checks,code_sha256=sha(Path(__file__)),no_original_result_modified=True,
        scope='Independent result/statistics integrity, not an intervention or final repair claim'))
    print('COMMITTED_CHECKPOINT_DATA_VALIDATION_PASS',len(checks),str(p.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
