"""Prospectively compare locked upstream roles with all four fixed prior policies."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
REFS=['legacy_safety_priority','legacy_pdms_priority','scale_1.005','scale_1.02']

def main():
    setup('vlm_repair/prior_reference_statistics');protocol=read(VOUT/'PRIOR_REFERENCE_PROTOCOL.json');assert protocol['reference_ids']==REFS
    old_folder=ROOT/'candidate_repair_v1/analysis/final_test';old=np.load(old_folder/'scores.npy',mmap_mode='r');old_arms=read(old_folder/'arms.json');oi={a['id']:i+1 for i,a in enumerate(old_arms)};old_rows=read(old_folder/'rows.json');sessions=np.array([r['session'] for r in old_rows]);names,inv=np.unique(sessions,return_inverse=True);counts=np.bincount(inv)
    rng=np.random.default_rng(20261016);draw=rng.integers(len(names),size=(2000,len(names)));signs=rng.choice([-1.,1.],size=(10000,len(names)));records=[]
    studies=[('primary',VOUT/'final/TEST_LOCK.json','final_test')]
    if (SEM/'repair/INFERENCE_COMPLETE.json').exists():studies.append(('semantic',SEM/'repair/TEST_LOCK.json','final_test_semantic'))
    else:assert (SEM/'repair/NO_COMPETITIVE_CANDIDATES.json').exists()
    late=VOUT/'late_token_coverage'
    if (late/'SCIENTIFIC_ACCEPTANCE.json').exists():studies.append(('late_token',late/'TEST_LOCK.json','final_test_late'))
    else:assert (late/'NO_COMPETITIVE_CANDIDATES.json').exists()
    neighbor=VOUT/'qda_neighbor_repair'
    if (neighbor/'SCIENTIFIC_ACCEPTANCE.json').exists():studies.append(('qda_neighbors',neighbor/'TEST_LOCK.json','final_test_qneighbor'))
    else:assert (neighbor/'NO_COMPETITIVE_CANDIDATES.json').exists()
    for study,lock_path,stage in studies:
        lock=read(lock_path);ids=list(dict.fromkeys(lock.get('primary_roles',lock.get('roles',{})).values()));folder=VOUT/'analysis'/stage;scores=np.load(folder/'scores.npy',mmap_mode='r');arms=read(folder/'arms.json');ai={a['id']:i+1 for i,a in enumerate(arms)}
        assert [r['token'] for r in read(folder/'rows.json')]==[r['token'] for r in old_rows] and np.array_equal(scores[:,:,0,:],old[:,:,0,:])
        for parent in ids:
            for reference in REFS:
                a=np.asarray(scores[:,:,ai[parent],:]);b=np.asarray(old[:,:,oi[reference],:]);delta=(a[:,:,0]-b[:,:,0]).mean(0);sums=np.bincount(inv,weights=delta,minlength=len(names));boot=sums[draw].sum(1)/counts[draw].sum(1)*100;p=(1+np.count_nonzero(signs@sums>=sums.sum()-1e-12))/(len(signs)+1)
                events={label:int((a[:,:,field]<1-1e-7).sum()-(b[:,:,field]<1-1e-7).sum()) for label,field in [('collision',1),('offroad',2),('ttc',4)]};events['zero']=int((a[:,:,0]<=1e-10).sum()-(b[:,:,0]<=1e-10).sum())
                records.append(dict(study=study,parent=parent,reference=reference,delta_pdms=float(delta.mean()*100),ci95=np.quantile(boot,[.025,.975]).tolist(),p_one_sided=float(p),net_events_vs_reference=events))
    maximum=0.
    for i,r in enumerate(sorted(records,key=lambda r:r['p_one_sided'])):maximum=max(maximum,min(1.,r['p_one_sided']*(len(records)-i)));r['p_holm']=maximum
    dest=VOUT/'prior_reference_statistics_four'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');atomic(dest/'SUMMARY.json',dict(status='PASS',time=stamp(),records=records,reference_ids=REFS,
        family='All unique locked global primary/semantic/late roles versus all four prospectively fixed prior policies; Holm jointly across studies. No best-prior selection using test.',
        protocol_sha256=sha(VOUT/'PRIOR_REFERENCE_PROTOCOL.json'),old_scores_sha256=sha(old_folder/'scores.npy'),baseline_all_seven_fields_exact=True));atomic(VOUT/'PRIOR_REFERENCE_LATEST.json',dict(path=str((dest/'SUMMARY.json').relative_to(ROOT))));print('PRIOR_REFERENCE_STATISTICS_PASS',len(records),str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
