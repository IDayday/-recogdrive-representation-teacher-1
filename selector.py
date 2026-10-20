"""Case-fixed privileged selection. Input [seeds,cases,Base+methods,7]."""
import numpy as np

FIELDS=['score','no_at_fault_collisions','drivable_area_compliance','ego_progress','time_to_collision_within_bound','comfort','driving_direction_compliance']

def choose(scores,mode='historical_failure_only',failure_lt=.7):
    a=np.asarray(scores)
    if a.ndim!=4 or a.shape[-1]!=7 or not np.isfinite(a).all():raise ValueError('Expected finite [S,N,K,7] matrix')
    base=a[:,:,0,:];failed=base[:,:,0]<failure_lt
    # np.argmax retains the first arm on ties, with Base first.
    if mode=='historical_failure_only':
        proposals=np.where(failed[:,:,None,None],a,base[:,:,None,:])
        index=proposals[:,:,:,0].mean(0).argmax(-1)
        chosen=proposals[:,np.arange(a.shape[1]),index,:]
    elif mode in ['teacher_consistent','teacher_safe']:
        eligible=np.ones(a.shape[1:3],dtype=bool)
        if mode=='teacher_safe':
            # Same genuine branch for every seed. No per-seed Oracle switching.
            eligible &= (a[:,:,:,0]>=base[:,:,None,0]-1e-12).all(0)
            for field in [1,2]:eligible &= ~((a[:,:,:,field]<1-1e-7)&(base[:,:,None,field]>=1-1e-7)).any(0)
            eligible &= ~((a[:,:,:,0]<=1e-10)&(base[:,:,None,0]>1e-10)).any(0)
        eligible[:,0]=True
        means=np.where(eligible,a[:,:,:,0].mean(0),-np.inf)
        index=means.argmax(-1);chosen=a[:,np.arange(a.shape[1]),index,:]
    else:raise ValueError(mode)
    return index,chosen

def summarize(chosen,base):
    after=chosen[:,:,0];before=base[:,:,0];failed=before<.7;high=before>.9
    result=dict(base_pdms=float(before.mean()*100),selected_pdms=float(after.mean()*100),delta_pdms=float((after-before).mean()*100),
        per_seed_delta_pdms=((after-before).mean(1)*100).tolist(),outputs=int(before.size),failure_outputs=int(failed.sum()),
        changed_outputs=int(np.any(chosen!=base,axis=-1).sum()),improved_outputs=int((after>before).sum()),worsened_outputs=int((after<before).sum()),
        repaired_to70=int((failed&(after>=.7)).sum()),repaired_above90=int((failed&(after>.9)).sum()),
        high_to_failure=int((high&(after<.7)).sum()),delta_failure_count=int((after<.7).sum()-failed.sum()),
        delta_zero_count=int((after<=1e-10).sum()-(before<=1e-10).sum()))
    for name,field in [('collision',1),('offroad',2),('ttc',4)]:
        b=base[:,:,field]<1-1e-7;c=chosen[:,:,field]<1-1e-7
        result.update({name+'_new':int((~b&c).sum()),name+'_removed':int((b&~c).sum()),name+'_net':int(c.sum()-b.sum())})
    return result
