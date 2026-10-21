"""Does repair capability survive conditioning on failure in all observed draws?

Outcome-defined strata are privileged diagnostics, never deployment features.
Three observed draws establish empirical repeatability, not permanent stability.
"""
from r2_common import *


def run(task):
    import numpy as np
    bank=read(ROOT/task['bank']);assert bank['mode']=='heldout';held=bank['heldout_fold'];point=read(ROOT/bank['point']);source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    with np.load(ROOT/bank['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);s=np.array(z['scores']);noise=np.array(z['seeds'])
    assert noise.tolist()==[0,1,2];base=s[:,0];masks=dict(observed_all3_failure=np.all(base[:,:,0]<.7,axis=1),observed_all3_high=np.all(base[:,:,0]>.9,axis=1),S0_failure=base[:,0,0]<.7)
    masks['S0_failure_with_at_least_one_later_nonfailure']=masks['S0_failure']&~masks['observed_all3_failure'];masks['other']=~(masks['observed_all3_failure']|masks['observed_all3_high'])
    allowed=np.asarray([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==held for r in rows]);assert np.all(allowed[ii]);cls=np.where(q[ii]<.7,0,np.where(q[ii]>.9,1,2));count=np.bincount(cls,minlength=3);population=np.array([np.sum(allowed&(q<.7)),np.sum(allowed&(q>.9)),np.sum(allowed&(q>=.7)&(q<=.9))]);w=np.asarray([population[c]/count[c] for c in cls]);w/=w.sum();out={}
    for configuration in point['policies']:
        policy=read(ROOT/configuration['policy']);pick=[0]+[ids.index(p['id']) for p in policy['parts']];c=s[:,pick];choice=c[:,:,:,0].argmax(1);oracle=c[np.arange(len(ii))[:,None],choice,np.arange(3)[None,:]];fixed=c[:,:,0,0].argmax(1);transfer=c[np.arange(len(ii)),fixed];result={}
        for name,mask in masks.items():
            n=int(mask.sum())
            if not n:result[name]=dict(cases=0);continue
            delta=oracle[mask,:,0]-base[mask,:,0];mass=float(w[mask].sum())
            result[name]=dict(cases=n,sessions=len({rows[int(i)]['session'] for i in ii[mask]}),estimated_population_mass=mass,
                Base_mean_PDMS_by_draw=(base[mask,:,0].mean(0)*100).tolist(),repair_oracle_PDMS_by_draw=(oracle[mask,:,0].mean(0)*100).tolist(),
                mean_conditional_oracle_gain_by_draw=(delta.mean(0)*100).tolist(),global_standardized_gain_contribution_by_draw=(np.sum(w[mask,None]*delta,axis=0)*100).tolist(),
                oracle_repaired90_by_draw=np.sum((base[mask,:,0]<.7)&(oracle[mask,:,0]>.9),axis=0).tolist(),
                S0_fixed_expert_repaired90_by_draw=np.sum((base[mask,:,0]<.7)&(transfer[mask,:,0]>.9),axis=0).tolist(),
                S0_fixed_expert_all3_above90=int(np.sum(np.all(transfer[mask,:,0]>.9,axis=1))),
                Base_three_draw_oracle_PDMS=float(base[mask,:,0].max(1).mean()*100),newly_damaged_high_per_candidate=[int(np.sum((base[mask,:,0]>.9)&(c[mask,a,:,0]<=.9))) for a in range(1,len(pick))])
        out[configuration['id']]=result
    path=ROOT/'analysis/held_stability_diagnostics'/(task['id']+'.json');atomic(path,dict(status='PRIVILEGED_HELD_DRAW_STABILITY_DIAGNOSTIC',time=stamp(),system=bank['system'],heldout_fold=held,counts={k:int(v.sum()) for k,v in masks.items()},comparisons=out,source_bank=task['bank'],source_matrix_sha256=bank['matrix_sha256'],observed_noise_indices=[0,1,2],caveat='Outcome-defined observed-three-draw strata; not a permanent-stability claim or a deployable trigger. Base3 versus repairK+1 is opportunity-matched only forK2/S0.',new_model_runs=0,validation_accessed=False,test_accessed=False));return dict(path=str(path.relative_to(ROOT)))
