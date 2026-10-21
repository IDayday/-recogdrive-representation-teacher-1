"""Separate trigger, candidate capability and cross-noise oracle diagnostics."""
from r2_common import *


def metrics(after,base,weights):
    import numpy as np
    delta=after[:,0]-base[:,0]
    return dict(standardized_pdms_gain=float(weights@delta*100),raw_mean_gain=float(delta.mean()*100),
        repaired70=int(np.sum((base[:,0]<.7)&(after[:,0]>=.7))),repaired90=int(np.sum((base[:,0]<.7)&(after[:,0]>.9))),
        lost_high=int(np.sum((base[:,0]>.9)&(after[:,0]<=.9))),damaged=int(np.sum(delta< -1e-8)),improved=int(np.sum(delta>1e-8)),
        new_collision=int(np.sum((after[:,1]<1)&(base[:,1]==1))),removed_collision=int(np.sum((after[:,1]==1)&(base[:,1]<1))),
        net_collision=int(np.sum(after[:,1]<1)-np.sum(base[:,1]<1)),net_offroad=int(np.sum(after[:,2]<1)-np.sum(base[:,2]<1)),
        net_zero=int(np.sum(after[:,0]==0)-np.sum(base[:,0]==0)),net_TTC=int(np.sum(after[:,3]<1)-np.sum(base[:,3]<1)),
        net_failure=int(np.sum(after[:,0]<.7)-np.sum(base[:,0]<.7)))


def run(task):
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);selection=read(ROOT/task['selection']);held=selection['heldout_fold']
    train=np.asarray([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows]);population=[np.sum(train&(quality<.7)),np.sum(train&(quality>.9)),np.sum(train&(quality>=.7)&(quality<=.9))]
    banks={};lineage=[]
    for tag,path in zip(['S0','noise'],task['responses']):
        response=read(ROOT/path)
        with np.load(ROOT/response['matrix']) as z:banks[tag]={k:np.array(z[k]) for k in ['global_indices','arm_ids','seeds','scores']}
        assert np.all(train[banks[tag]['global_indices']]);lineage.append(dict(path=path,matrix_sha256=response['matrix_sha256']))
    def weights(ii):
        c=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));count=np.bincount(c,minlength=3);w=np.asarray([population[v]/count[v] for v in c]);return w/w.sum()
    output={}
    for role in ['PDMS','safety']:
        ids=['baseline']+[v for _,v in sorted(selection['policies'][role].items(),key=lambda p:int(p[0]))];fixed={a:[] for a in ids[1:]};oracle=[];safe_oracle=[]
        for tag in ['S0','noise']:
            data=banks[tag];ii=data['global_indices'];aa=list(data['arm_ids']);score=data['scores'][:,[aa.index(i) for i in ids]];w=weights(ii)
            for n,noise in enumerate(data['seeds']):
                s=score[:,:,n];base=s[:,0];choice=s[:,:,0].argmax(1);chosen=s[np.arange(len(s)),choice]
                allowed=(s[:,:,1]>=base[:,None,1])&(s[:,:,2]>=base[:,None,2])&~((s[:,:,0]==0)&(base[:,None,0]>0))
                safe_choice=np.where(allowed,s[:,:,0],-np.inf).argmax(1);safe=s[np.arange(len(s)),safe_choice]
                assert np.all(chosen[:,0]>=base[:,0]) and np.all(safe[:,0]>=base[:,0])
                oracle.append(dict(seed=int(noise),metrics=metrics(chosen,base,w),expert_use=np.bincount(choice,minlength=len(ids)).tolist()))
                safe_oracle.append(dict(seed=int(noise),metrics=metrics(safe,base,w)))
                for a,ident in enumerate(ids[1:],1):
                    after=s[:,a];mask=np.where((base[:,0]<.7)[:,None],after,base);beneficial=np.where((after[:,0]>base[:,0])[:,None],after,base)
                    fixed[ident].append(dict(seed=int(noise),unconditional=metrics(after,base,w),perfect_failure_trigger=metrics(mask,base,w),benefit_only_privileged_trigger=metrics(beneficial,base,w)))
        s0=banks['S0'];noise=banks['noise'];positions={int(i):j for j,i in enumerate(s0['global_indices'])};ii=noise['global_indices'];jj=np.asarray([positions[int(i)] for i in ii]);w=weights(ii)
        a0=[list(s0['arm_ids']).index(a) for a in ids];an=[list(noise['arm_ids']).index(a) for a in ids];first=s0['scores'][jj][:,a0,0];later=noise['scores'][:,an];fixed_choice=first[:,:,0].argmax(1)
        all_score=np.concatenate([first[:,:,None,:],later],2);scene_choice=all_score[:,:,:,0].mean(2).argmax(1);transfer=[]
        for n,seed_index in enumerate([0]+noise['seeds'].tolist()):
            s=all_score[:,:,n];base=s[:,0];after=s[np.arange(len(s)),fixed_choice];scene=s[np.arange(len(s)),scene_choice]
            transfer.append(dict(seed=int(seed_index),S0_selected_fixed_expert=metrics(after,base,w),all_noise_privileged_fixed_expert=metrics(scene,base,w)))
        output[role]=dict(nonzero_modules=len(ids)-1,identity_additional=True,draw_oracle=oracle,per_output_safety_oracle=safe_oracle,
            fixed_raw_candidates=fixed,scene_fixed_transfer=transfer,paired_transfer_cases=len(ii),candidate_ids=ids)
    path=ROOT/'analysis/bank_potential'/task['id'];atomic(path.with_suffix('.json'),dict(status='TRAINING_LIBRARY_DIAGNOSTIC',time=stamp(),selection=task['selection'],system=selection['system'],heldout_fold=held,
        roles=output,sources=lineage,privileged=True,deployable_performance=False,
        standardization='S0-quality class proportions only. Session-balanced panels are not a full natural-population estimate.',
        oracle_scope='Frozen per-role K experts; not the whole internal parameter search, not a theoretical upper bound.',
        safety_oracle_scope='Per-output NC/DAC value and zero-score nonworsening; stricter than global net count constraints.',
        trigger_distinction='True Base failure alone versus knowing actual benefit; neither supplies deployable outcome information.',validation_accessed=False,test_accessed=False))
    return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),system=selection['system'],heldout_fold=held)
