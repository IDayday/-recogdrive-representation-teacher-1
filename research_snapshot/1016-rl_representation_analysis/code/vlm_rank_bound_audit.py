"""Audit committed residual ranks against their independent algebraic bound."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_repair/rank_bound_audit');checks=[]
    for source in [VOUT,VOUT/'early_interface',SEM]:
        config=source/'scan/CONFIGS.json'
        if not config.exists():continue
        entries=read(config)
        for path in sorted((source/'scan/results').glob('*.json')):
            result=read(path)
            if result['status']!='COMPLETE':continue
            d=result['dimension']
            bounds=np.array([min(c['kf'],max(0,d-c['ks'])) if c['kind'].endswith('residual') else 65535 for c in entries])
            requested=np.array([c['r'] or 0 for c in entries])
            with np.load(ROOT/result['array_path']) as z:
                over=z['ranks'][:,:,:,2]>bounds[None,None,:]
                valid=(z['status']==0).all(1)&~z['cutoff_degenerate'].any(1)
                bad=valid&(requested[None,:]>bounds[None,:])
            checks.append(dict(result_path=str(path.relative_to(ROOT)),result_sha256=sha(path),
                reported_fold_ranks_exceeding_algebraic_bound=int(over.sum()),
                eligible_non_degenerate_requested_r_exceeding_bound=int(bad.sum())))
    assert checks
    bad=[c for c in checks if c['reported_fold_ranks_exceeding_algebraic_bound'] or c['eligible_non_degenerate_requested_r_exceeding_bound']]
    assert not bad,bad
    dest=VOUT/'audits'/('rank_bound_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(dest,dict(status='PASS',time=stamp(),checks=checks,rule='residual rank <= min(kf,D-ks), all folds and centers',
        models_rerun=False,code_sha256=sha(Path(__file__))))
    atomic(VOUT/'RANK_BOUND_AUDIT_LATEST.json',dict(path=str(dest.relative_to(ROOT))))
    print('FULL_GRID_ALGEBRAIC_RANK_BOUND_PASS',len(checks),str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
