"""Session-cluster uncertainty and failure-mode ledgers, derived from accepted scores only."""
from common import *
import argparse
import numpy as np

def details(name):
    path=ROOT/'repair_v1/analysis'/name;data=np.load(path/'scores.npy',mmap_mode='r')
    rows=read(path/'rows.json');arms=read(path/'arms.json');baseline=np.asarray(data[:,:,0]);n=len(rows)
    sessions=np.array([r['session'] for r in rows]);unique=np.unique(sessions)
    groups=[np.flatnonzero(sessions==s) for s in unique];counts=np.array([len(g) for g in groups])
    rng=np.random.default_rng(20261016);draw=rng.integers(len(groups),size=(500,len(groups)))
    def clustered(values,factor=100):
        values=np.asarray(values).mean(0);sums=np.array([values[g].sum() for g in groups])
        boot=sums[draw].sum(1)/counts[draw].sum(1)*factor
        return dict(mean=float(values.mean()*factor),ci95=np.quantile(boot,[.025,.975]).tolist())
    output=[]
    for index,a in enumerate(arms,1):
        current=np.asarray(data[:,:,index]);failure=baseline[:,:,0]<.7;events={}
        for key,col in [('collision',1),('offroad',2),('ttc',4)]:
            before=baseline[:,:,col]<1;after=current[:,:,col]<1
            events[key+'_net_pp']=clustered(after.astype(float)-before.astype(float))
            events[key+'_new_pp']=clustered(~before&after)
            events[key+'_removed_pp']=clustered(before&~after)
        before=baseline[:,:,0]==0;after=current[:,:,0]==0
        events['zero_net_pp']=clustered(after.astype(float)-before.astype(float))
        stable_failure=np.broadcast_to((baseline[:,:,0]<.7).all(0),failure.shape)
        stable_success=np.broadcast_to((baseline[:,:,0]>.9).all(0),failure.shape)
        fixed_s0=np.broadcast_to(baseline[0,:,0]<.7,failure.shape)
        modes={'all_failure':failure,'collision':failure&(baseline[:,:,1]<1),'offroad':failure&(baseline[:,:,2]<1),
            'ttc':failure&(baseline[:,:,4]<1),'low_progress':failure&(baseline[:,:,3]<.5),
            'stable_failure_all_sampling_seeds':stable_failure,'fixed_S0_failure_cohort':fixed_s0}
        by_mode={}
        for mode,mask in modes.items():
            total=int(mask.sum());delta=current[:,:,0]-baseline[:,:,0]
            by_mode[mode]=dict(nonexclusive=True,stochastic_outputs=total,
                repair_ge70=int((mask&(current[:,:,0]>=.7)).sum()),repair_gt90=int((mask&(current[:,:,0]>.9)).sum()),
                mean_delta_pdms=float(delta[mask].mean()*100) if total else None)
        fixed=[]
        for j in range(data.shape[0]):
            mask=fixed_s0[j]
            fixed.append(dict(seed_position=j,cases=int(mask.sum()),baseline_gt90=int((mask&(baseline[j,:,0]>.9)).sum()),
                edited_gt90=int((mask&(current[j,:,0]>.9)).sum()),
                matched_new_gt90=int((mask&(baseline[j,:,0]<=.9)&(current[j,:,0]>.9)).sum()),
                matched_lost_gt90=int((mask&(baseline[j,:,0]>.9)&(current[j,:,0]<=.9)).sum())))
        output.append(dict(arm_id=a['id'],uncertainty=events,by_mode=by_mode,fixed_S0_cohort_by_seed=fixed,
            stable_success_damage=dict(cases=int(stable_success[0].sum()),sampling_outputs=int(stable_success.sum()),
                to_le90=int((stable_success&(current[:,:,0]<=.9)).sum()),to_failure=int((stable_success&(current[:,:,0]<.7)).sum()))))
    doc=dict(status='COMPLETE',time=stamp(),stage=name,scenes=n,sessions=len(unique),seeds=data.shape[0],
        score_matrix_sha256=sha(path/'scores.npy'),bootstrap='500 acquisition-session cluster resamples, averaging sampling seeds inside each scene',
        progress_mode='baseline PDMS<70 and ego_progress<0.5, may overlap other failure modes',records=output)
    target=path/'DETAILS.json'
    assert not target.exists();atomic(target,doc)
    return doc

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);args=p.parse_args();setup('repair/details')
    d=details(args.stage);print(json.dumps(dict(stage=args.stage,arms=len(d['records']),status=d['status'])))
