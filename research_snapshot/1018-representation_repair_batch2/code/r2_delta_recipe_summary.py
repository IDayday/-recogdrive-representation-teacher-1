"""Compare causal-space regression by actual outcomes, never MSE alone."""
from r2_common import *


def run(task):
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    mask=np.array([r['subset']=='exploration' for r in rows]);population=[np.sum(mask&(quality<.7)),np.sum(mask&(quality>.9)),np.sum(mask&(quality>=.7)&(quality<=.9))]
    summaries=[]
    for stage in ['delta_calibration_eval_v1','delta_fullinput_eval_v1']:
        for path in (ROOT/'analysis/responses'/stage).glob('*.json'):
            response=read(path);point=read(ROOT/response['point']);arms={a['id']:a for a in point['arms']}
            with np.load(ROOT/response['matrix']) as z:s=np.array(z['scores']);ii=np.array(z['global_indices']);ids=list(z['arm_ids'])
            classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
            w=np.asarray([population[c]/counts[c] for c in classes]);w/=w.sum()
            for j,ident in enumerate(ids[1:],1):
                a=s[:,j];b=s[:,0];delta=a[:,:,0]-b[:,:,0]
                metrics=dict(weighted_pdms_gain=float(np.sum(w[:,None]*delta)/delta.shape[1])*100,
                    enriched_failure_gain=float(delta[classes==0].mean()*100),high_gain=float(delta[classes==1].mean()*100),
                    weighted_collision_delta=float(np.sum(w[:,None]*((a[:,:,1]<1).astype(float)-(b[:,:,1]<1).astype(float)))/delta.shape[1]),
                    weighted_offroad_delta=float(np.sum(w[:,None]*((a[:,:,2]<1).astype(float)-(b[:,:,2]<1).astype(float)))/delta.shape[1]),
                    weighted_zero_delta=float(np.sum(w[:,None]*((a[:,:,0]==0).astype(float)-(b[:,:,0]==0).astype(float)))/delta.shape[1]))
                summaries.append(dict(stage=stage,arm=ident,configuration=arms[ident],**metrics))
    summaries.sort(key=lambda d:d['weighted_pdms_gain'],reverse=True)
    output=ROOT/'analysis/delta_calibration/SUMMARY.json';atomic(output,dict(status='EXPLORATORY_ACTUAL_SCORE_SUMMARY',time=stamp(),settings=len(summaries),
        best=summaries[:30],best_failure=sorted(summaries,key=lambda d:d['enriched_failure_gain'],reverse=True)[:30],
        all_settings=summaries,small_panel=True,selection_not_independent=True,validation_accessed=False,test_accessed=False))
    return dict(path=str(output.relative_to(ROOT)),settings=len(summaries))
