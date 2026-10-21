"""Conservative search correction includes uncomputed planned hypotheses as p=1."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def correction(p,bound):
    order=np.argsort(p,kind='stable');ordered=p[order];ranks=np.arange(1,len(p)+1);bh=np.minimum.accumulate((ordered*bound/ranks)[::-1])[::-1]
    harmonic=float(np.euler_gamma+np.log(bound)+1/(2*bound)-1/(12*bound*bound));by=np.minimum(bh*harmonic,1);a=np.empty(len(p));b=np.empty(len(p));a[order]=np.minimum(bh,1);b[order]=by;return a,b

def main():
    setup('vlm_repair/multiple_comparisons');groups=[];bound=0;pv=[];identity=[]
    for folder,cells in [(VOUT/'scan',2272),(VOUT/'rapid',2272),(SEM/'scan',64),(SEM/'rapid',64)]:
        if not (folder/'CONFIGS.json').exists():m=11633 if folder.name=='scan' else 81
        else:m=len(read(folder/'CONFIGS.json'))
        bound+=cells*(m*2+4)
        completed=0;finite=0
        for p in sorted((folder/'results').glob('*.json')):
            r=read(p);completed+=1
            if r['status']!='COMPLETE':continue
            with np.load(ROOT/r['array_path']) as data:
                primary=data['metrics'][:,5,:,6].reshape(-1);secondary=data['secondary_metrics'][:,5,:,6].reshape(-1)
            a=np.r_[primary,secondary];valid=np.flatnonzero(np.isfinite(a));pv.extend(a[valid].tolist());identity.extend((str(p.relative_to(ROOT)),int(i)) for i in valid);finite+=len(valid)
        groups.append(dict(root=str(folder.relative_to(ROOT)),planned_cells=cells,completed_cells=completed,configs_per_center=m,finite_hypotheses=finite))
    p=np.asarray(pv);assert len(p)<=bound and ((p>=0)&(p<=1)).all();bh,by=correction(p,bound)
    # Never overwrite a previous analysis snapshot as the queue grows.
    folder=VOUT/'multiplicity'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');folder.mkdir(parents=True,exist_ok=False)
    np.savez(folder/'search_correction.npz',p=p,bh=bh,by=by);atomic(folder/'identities.json',identity)
    confirmation=[read(f) for f in (VOUT/'confirmation').glob('*.json')];valid=[c for c in confirmation if c['metrics'].get('session_p') is not None];assert len(valid)<=1000
    indices=sorted(range(len(valid)),key=lambda i:valid[i]['metrics']['session_p']);highest=0.
    heldout=[]
    for rank,i in enumerate(indices):
        c=valid[i];highest=max(highest,min(1.,c['metrics']['session_p']*(1000-rank)));m=c['metrics'];heldout.append(dict(id=c['id'],cell=c['cell'],p_holm_planned1000=highest,auc=m['auc'],weighted_ap=m['weighted_ap'],standardized_gap=m['standardized_gap'],
            passes_distribution_criteria=bool(m['auc'] is not None and m['auc']>=.6 and m['standardized_gap'] is not None and m['standardized_gap']>=.2 and m['weighted_ap']>m['class_prevalence'] and m['session_positive_fraction']>=.65),secondary_seeds=c['secondary_seeds']))
    atomic(folder/'SUMMARY.json',dict(status='PASS',time=stamp(),searches=groups,planned_hypothesis_bound=bound,observed_finite=len(p),bh_discoveries=int((bh<=.05).sum()),by_discoveries=int((by<=.05).sum()),uncomputed_and_ineligible='p=1 conservatively in denominator; completion not implied',heldout_confirmation=heldout,
        correction_scope='Search distribution tests only; intervention outcome hypotheses corrected separately; significance alone never identifies a repairable mechanism.',invalid_original_semantic_cells_excluded_from_interpretation=True))
    print('MULTIPLICITY_SNAPSHOT_PASS',len(p),bound,str(folder.relative_to(ROOT)))
if __name__=='__main__':main()
