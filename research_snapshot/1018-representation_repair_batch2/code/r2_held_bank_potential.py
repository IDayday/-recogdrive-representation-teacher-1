"""Actual fold-held candidate capability versus observable routing, fixed K."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_bank_potential import metrics
    bank=read(ROOT/task['bank']);assert bank['mode']=='heldout';point=read(ROOT/bank['point']);held=bank['heldout_fold']
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    mask=np.asarray([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5==held for r in rows])
    with np.load(ROOT/bank['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);seeds=np.array(z['seeds']);scores=np.array(z['scores'])
    assert np.all(mask[ii]) and seeds.tolist()==[0,1,2]
    population=np.asarray([np.sum(mask&(quality<.7)),np.sum(mask&(quality>.9)),np.sum(mask&(quality>=.7)&(quality<=.9))]);classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
    w=np.asarray([population[c]/counts[c] for c in classes]);w/=w.sum();output={}
    for config in point['policies']:
        policy=read(ROOT/config['policy']);assert policy['heldout_fold']==held
        allowed=['baseline']+[p['id'] for p in policy['parts']];a=[ids.index(v) for v in allowed];s=scores[:,a];oracle=[];safe_oracle=[];fixed={v:[] for v in allowed[1:]}
        chosen0=s[:,:,0,0].argmax(1);by_scene=s[:,:,:,0].mean(2).argmax(1);transfer=[]
        for n,noise in enumerate(seeds):
            actual=s[:,:,n];base=actual[:,0];pick=actual[:,:,0].argmax(1);after=actual[np.arange(len(ii)),pick]
            safe=(actual[:,:,1]>=base[:,None,1])&(actual[:,:,2]>=base[:,None,2])&~((actual[:,:,0]==0)&(base[:,None,0]>0))
            safe_pick=np.where(safe,actual[:,:,0],-np.inf).argmax(1);safe_after=actual[np.arange(len(ii)),safe_pick]
            oracle.append(dict(seed=int(noise),metrics=metrics(after,base,w),expert_use=np.bincount(pick,minlength=len(allowed)).tolist()))
            safe_oracle.append(dict(seed=int(noise),metrics=metrics(safe_after,base,w)))
            for j,ident in enumerate(allowed[1:],1):
                value=actual[:,j];triggered=np.where((base[:,0]<.7)[:,None],value,base);positive=np.where((value[:,0]>base[:,0])[:,None],value,base)
                fixed[ident].append(dict(seed=int(noise),unconditional=metrics(value,base,w),perfect_failure_trigger=metrics(triggered,base,w),benefit_only_privileged_trigger=metrics(positive,base,w)))
            transfer.append(dict(seed=int(noise),S0_fixed_expert=metrics(actual[np.arange(len(ii)),chosen0],base,w),all_three_noise_privileged_fixed_expert=metrics(actual[np.arange(len(ii)),by_scene],base,w)))
        output[config['id']]=dict(nonzero_modules=len(allowed)-1,identity_additional=True,candidate_ids=allowed,draw_oracle=oracle,strict_per_output_safety_oracle=safe_oracle,fixed_raw_candidates=fixed,scene_fixed_transfer=transfer,
            observable_policy=str(config['policy']))
    path=ROOT/'analysis/held_bank_potential'/(task['id']+'.json')
    atomic(path,dict(status='HELD_SESSION_PRIVILEGED_DIAGNOSTIC',time=stamp(),system=bank['system'],heldout_fold=held,cases=len(ii),roles=output,
        source_bank=task['bank'],source_sha256=sha(ROOT/task['bank']),matrix_sha256=bank['matrix_sha256'],
        deployable=False,held_outcomes_only_for_diagnosis=True,complete_five_folds=False,
        scope='Frozen per-role K candidates plus Base on one held fold; class-standardized session-balanced sampled panel, not a natural-population result or theoretical upper bound.',
        safety_scope='Per-output NC/DAC value and zero nonworsening; not global net-count feasibility.',validation_accessed=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)),system=bank['system'],heldout_fold=held)
