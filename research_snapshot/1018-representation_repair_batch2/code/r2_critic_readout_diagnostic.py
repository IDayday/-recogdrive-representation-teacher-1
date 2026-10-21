"""Read-only calibration-to-held quality/gain readout diagnostics.

Uses exact stored true candidate outcomes. No retuning on held labels. Noise
rows are descriptive paired repeats; no independent-scene p value is inferred.
"""
from r2_common import *


def run(task):
    import numpy as np
    from sklearn.metrics import roc_auc_score,average_precision_score
    from r2_token_policy_select import matrices,choices
    policy=read(ROOT/task['policy']);heldpoint=read(ROOT/task['held_point']);calpoint=read(ROOT/policy['source_point']);data={};source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    result={}
    for mode,point,stage in [('calibration',calpoint,task['calibration_stage']),('heldout',heldpoint,task['held_stage'])]:
        d,lineage=matrices(point,stage);ix=d['global_indices'];score=d['scores'];selected_index=policy['selected_calibration']['critic_index'] if mode=='calibration' else 0
        pred=d['predicted'][:,selected_index];gain=score[:,1:,0]-score[:,:1,0];pg=pred[:,1:,0]-pred[:,:1,0];risk=np.maximum(pred[:,:1,1:3]-pred[:,1:,1:3],0).sum(2)
        utility=np.clip(pg,-1.,1.)-policy['critic']['risk_penalty']*risk;trigger=utility.max(1);best=gain.max(1)
        cls=np.where(q[ix]<.7,0,np.where(q[ix]>.9,1,2));held=policy['heldout_fold'];mask=np.array([r['subset']=='exploration' and ((int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==held) if mode=='heldout' else (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held)) for r in rows])
        population=np.array([np.sum(mask&(q<.7)),np.sum(mask&(q>.9)),np.sum(mask&(q>=.7)&(q<=.9))]);counts=np.bincount(cls,minlength=3);w=np.array([population[c]/counts[c] for c in cls]);w/=w.sum()
        route=choices(pred,policy['critic']['risk_penalty'],policy['critic']['threshold']);chosen=score[np.arange(len(ix)),route];base=score[:,0]
        def quality(y,estimate,weight):
            if len(np.unique(y))<2:return dict(AUROC=None,AP=None,weighted_positive_fraction=float(weight@y/weight.sum()))
            return dict(AUROC=float(roc_auc_score(y,estimate,sample_weight=weight)),AP=float(average_precision_score(y,estimate,sample_weight=weight)),weighted_positive_fraction=float(weight@y/weight.sum()))
        thresholds={}
        for threshold in [0.,.01,.05,.1]:
            label=best>threshold;thresholds[str(threshold)]=dict(all=quality(label,trigger,w),by_class={str(c):quality(label[cls==c],trigger[cls==c],w[cls==c]) for c in range(3)})
        classes={}
        for c in range(3):
            m=cls==c;z=w[m]/w[m].sum();active=route[m]>0;dd=chosen[m,0]-base[m,0]
            classes[str(c)]=dict(rows=int(m.sum()),weighted_actual_gain=float(z@dd*100),weighted_oracle_gain=float(z@np.maximum(best[m],0)*100),active_fraction=float(z@active),
                beneficial_active_fraction=float(z@((dd>1e-8)&active)),harmful_active_fraction=float(z@((dd< -1e-8)&active)),
                mean_predicted_max_gain=float(z@pg[m].max(1)),mean_actual_best_gain=float(z@best[m]))
        result[mode]=dict(cases=len(set(ix.tolist())),noise_rows=len(ix),sessions=len({rows[int(i)]['session'] for i in ix}),benefit_trigger_quality=thresholds,classes=classes,
            weighted_total_gain=float(w@(chosen[:,0]-base[:,0])*100),weighted_oracle_gain=float(w@np.maximum(best,0)*100),active_fraction=float(w@(route>0)),lineage=lineage)
    folder=ROOT/'analysis/critic_readout_diagnostics';path=folder/(task['id']+'.json');atomic(path,dict(status='DESCRIPTIVE_READOUT_DIAGNOSTIC',time=stamp(),task=task,policy_system=policy['system'],role=policy['role'],context_view=policy.get('context_view','post_valid'),heldout_fold=policy['heldout_fold'],metrics=result,
        caveats=['All numbers are developmental outer-fold evidence; no tuning on held labels.','Natural-class standardization does not turn enriched panels into complete natural evaluation.','Three noise rows share a scene; no independence or causal information-sufficiency claim.'],validation_accessed=False,test_accessed=False));return dict(path=str(path.relative_to(ROOT)))
