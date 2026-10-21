"""Refresh the entire exploratory family including the frozen quadratic controls."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_qda_controls_v2 import OUT,configs
from vlm_multiple_comparisons import correction
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_repair/qda_joint');protocol=read(OUT/'PROTOCOL.json');results=[]
    for site in protocol['sites']:
        p=OUT/'results'/(site['fit']['cell']+'.json');d=read(p);assert d['status']=='PASS' and d['original_parent_cv_reproduced'];results.append((p,d))
    # Obtain a current snapshot, including all then-completed original/SEM scans
    # and every frozen hold-out confirmation (80 new controls, max family 1000).
    import vlm_multiple_comparisons
    vlm_multiple_comparisons.main();source=sorted((VOUT/'multiplicity').glob('*/SUMMARY.json'))[-1];summary=read(source)
    with np.load(source.parent/'search_correction.npz') as z:p=np.array(z['p'])
    identities=read(source.parent/'identities.json');extra=[]
    for path,d in results:
        for i,r in enumerate(d['records']):
            if r['cv']['session_p'] is not None:extra.append(r['cv']['session_p']);identities.append([str(path.relative_to(ROOT)),i])
    values=np.r_[p,extra];bound=summary['planned_hypothesis_bound']+len(protocol['sites'])*len(configs());bh,by=correction(values,bound)
    destination=VOUT/'multiplicity'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'_qda');destination.mkdir(parents=True,exist_ok=False)
    np.savez(destination/'search_correction.npz',p=values,bh=bh,by=by);atomic(destination/'identities.json',identities)
    summary.update(time=stamp(),planned_hypothesis_bound=bound,observed_finite=len(values),bh_discoveries=int((bh<=.05).sum()),by_discoveries=int((by<=.05).sum()),
        qda_control_protocol_sha256=sha(OUT/'PROTOCOL.json'),qda_source_snapshot=str(source.relative_to(ROOT)),all_qda_control_sites_complete=True,
        exploratory_duplicates='Parent PCA128 comparisons occur in both original and control audit; retained twice conservatively in planned denominator, never independent cases.')
    summary['searches'].append(dict(root=str(OUT.relative_to(ROOT)),planned_cells=4,completed_cells=4,configs_per_center=21,finite_hypotheses=len(extra),centering='one frozen exploration-selected centering per site'))
    atomic(destination/'SUMMARY.json',summary);atomic(OUT/'JOINT_LATEST.json',dict(path=str((destination/'SUMMARY.json').relative_to(ROOT))))
    print('QDA_FULL_FAMILY_CORRECTION_PASS',len(values),bound,str(destination.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
