"""Frozen second-round contrasts, paired seed/session inference, stable-case outcomes."""
from common import *
import numpy as np
from candidate_repair_fit import OUT

def main():
    setup('candidate_repair/statistics')
    cfg=read(OUT/'FINAL_TEST_LOCK.json');folder=OUT/'analysis/final_test';rows=read(folder/'rows.json');arms=read(folder/'arms.json')
    scores=np.load(folder/'scores.npy',mmap_mode='r');ai={'baseline':0,**{a['id']:i+1 for i,a in enumerate(arms)}}
    old=np.load(ROOT/'repair_v1/analysis/final_test/scores.npy',mmap_mode='r');assert np.array_equal(scores[:,:,0],old[:,:,0])
    sessions=np.array([r['session'] for r in rows]);unique,inv=np.unique(sessions,return_inverse=True);counts=np.bincount(inv)
    rng=np.random.default_rng(cfg['inference_seed']);draw=rng.integers(len(unique),size=(cfg['bootstrap'],len(unique)));signs=rng.choice([-1.,1.],size=(cfg['sign_flips'],len(unique)))
    records=[]
    for c in cfg['contrasts']:
        positive=np.asarray(scores[:,:,[ai[a] for a in c['positive']],0]).mean(2)
        reference=np.asarray(scores[:,:,[ai[a] for a in c['reference']],0]).mean(2)
        delta=(positive-reference).mean(0);sums=np.bincount(inv,weights=delta,minlength=len(unique))
        boot=sums[draw].sum(1)/counts[draw].sum(1)*100
        p=(1+np.count_nonzero(signs@sums>=sums.sum()-1e-12))/(cfg['sign_flips']+1)
        records.append(dict(**c,delta_pdms=float(delta.mean()*100),ci95=np.quantile(boot,[.025,.975]).tolist(),p_one_sided=float(p)))
    for family in sorted({r['family'] for r in records}):
        group=[i for i,r in enumerate(records) if r['family']==family];order=sorted(group,key=lambda i:records[i]['p_one_sided']);maximum=0.
        for j,i in enumerate(order):
            maximum=max(maximum,min(1.,records[i]['p_one_sided']*(len(order)-j)));records[i]['p_holm']=maximum
    baseline=scores[:,:,0,0];stable_fail=(baseline<.7).all(0);stable_high=(baseline>.9).all(0);details=[]
    failure_modes={};remaining=baseline<.7
    for name,field in [('collision',1),('offroad',2),('ttc',4)]:
        mask=remaining&(scores[:,:,0,field]<1);failure_modes[name]=mask;remaining=remaining&~mask
    failure_modes['progress_or_other']=remaining
    for i,a in enumerate(arms,1):
        after=scores[:,:,i,0];before_fail=baseline<.7;before_high=baseline>.9
        events={}
        for label,field in [('collision',1),('offroad',2),('ttc',4)]:
            b=scores[:,:,0,field]<1;e=scores[:,:,i,field]<1
            event=dict(before=int(b.sum()),after=int(e.sum()),new=int((~b&e).sum()),removed=int((b&~e).sum()),net=int(e.sum()-b.sum()))
            case_gap=(e.astype(float)-b.astype(float)).mean(0);ss=np.bincount(inv,weights=case_gap,minlength=len(unique))
            event['event_rate_change_ci95']=np.quantile(ss[draw].sum(1)/counts[draw].sum(1),[.025,.975]).tolist();events[label]=event
        b=baseline==0;e=after==0;events['zero']=dict(before=int(b.sum()),after=int(e.sum()),new=int((~b&e).sum()),removed=int((b&~e).sum()),net=int(e.sum()-b.sum()))
        by_mode={name:dict(outputs=int(mask.sum()),repaired_ge70=int((mask&(after>=.7)).sum()),repaired_gt90=int((mask&(after>.9)).sum()),
            mean_delta_pdms=float((after-baseline)[mask].mean()*100) if mask.any() else None) for name,mask in failure_modes.items()}
        details.append(dict(arm=a['id'],method=a['method'],route=a.get('route'),control=a.get('control',False),failure_modes=by_mode,
            mean_pdms=float(after.mean()*100),delta_pdms=float((after-baseline).mean()*100),
            repaired_ge70=int((before_fail&(after>=.7)).sum()),repaired_gt90=int((before_fail&(after>.9)).sum()),
            high_to_failure=int((before_high&(after<.7)).sum()),high_to_le90=int((before_high&(after<=.9)).sum()),
            total_failures=int((after<.7).sum()),failure_net=int((after<.7).sum()-before_fail.sum()),events=events,
            stable_fail_cases=int(stable_fail.sum()),stable_fail_ge70=int((after[:,stable_fail]>=.7).sum()),stable_fail_gt90=int((after[:,stable_fail]>.9).sum()),
            stable_high_cases=int(stable_high.sum()),stable_high_to_failure=int((after[:,stable_high]<.7).sum()),
            new_failure_from_nonfailure=int(((baseline>=.7)&(after<.7)).sum())))
    result=dict(status='PASS',time=stamp(),protocol_sha256=sha(OUT/'FINAL_TEST_LOCK.json'),records=records,details=details,
        baseline=dict(mean_pdms=float(baseline.mean()*100),mean_by_seed=(baseline.mean(1)*100).tolist(),failure_outputs=int((baseline<.7).sum()),high_outputs=int((baseline>.9).sum())),
        legacy_base_exact=True,test_reused_from_previous_round=True,seed_case_unit='Five samples are not five independent trainings or independent cases',
        failure_mode_definition='Hierarchical partition of failed baseline outputs: collision, then offroad, then TTC, then progress/other; not causal attribution')
    atomic(folder/'FINAL_STATISTICS.json',result);print(json.dumps(dict(status='PASS',contrasts=len(records),arms=len(arms))),flush=True)

if __name__=='__main__':main()
