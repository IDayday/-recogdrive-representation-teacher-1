"""Case/session inference and precision/repair ledgers for frozen VLM policies."""
from common import *
import numpy as np
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_oracle_extended import detail


def comparisons(folder,lock,semantic=False):
    scores=np.load(folder/'scores.npy',mmap_mode='r');rows=read(folder/'rows.json');arms=read(folder/'arms.json');base=np.asarray(scores[:,:,0,:]);original=np.load(ROOT/'candidate_repair_v1/analysis/final_test/scores.npy',mmap_mode='r');assert np.array_equal(base,original[:,:,0,:])
    ai={'baseline':0,**{a['id']:i+1 for i,a in enumerate(arms)}};sessions=np.array([r['session'] for r in rows]);names,inv=np.unique(sessions,return_inverse=True);counts=np.bincount(inv);rng=np.random.default_rng(20261016);draw=rng.integers(len(names),size=(2000,len(names)));signs=rng.choice([-1.,1.],size=(10000,len(names)));records=[]
    role_ids=list(dict.fromkeys(lock.get('primary_roles',lock.get('roles',{})).values()))
    contrasts=[dict(id='gain_'+p,family='primary',positive=[p],reference=['baseline']) for p in role_ids]
    for p in role_ids:
        reverse=[a['id'] for a in arms if a.get('control_parent')==p and a.get('control_kind')=='reverse'];haar=[a['id'] for a in arms if a.get('control_parent')==p and a.get('control_kind')=='haar_rotation']
        if reverse:contrasts.append(dict(id='reverse_'+p,family='direction',positive=[p],reference=reverse))
        if haar:assert len(haar)==3;contrasts.append(dict(id='haar_'+p,family='direction',positive=[p],reference=haar))
    for p in set(lock.get('component_diagnostics',{}).values())-set(role_ids):contrasts.append(dict(id='component_'+p,family='component_diagnostic',positive=[p],reference=['baseline']))
    for c in contrasts:
        value=np.asarray(scores[:,:,[ai[i] for i in c['positive']],0]).mean(2);reference=np.asarray(scores[:,:,[ai[i] for i in c['reference']],0]).mean(2);delta=(value-reference).mean(0);sums=np.bincount(inv,weights=delta,minlength=len(names));boot=sums[draw].sum(1)/counts[draw].sum(1)*100
        p=(1+np.count_nonzero(signs@sums>=sums.sum()-1e-12))/(len(signs)+1);records.append(dict(**c,study='semantic_correction' if semantic else 'primary',delta_pdms=float(delta.mean()*100),ci95=np.quantile(boot,[.025,.975]).tolist(),p_one_sided=float(p)))
    edits=np.load(folder/'edits.npy',mmap_mode='r');methods=[];best=base.copy();failure=base[:,:,0]<.7
    for i,a in enumerate(arms,1):
        value=np.asarray(scores[:,:,i,:]);delta=value[:,:,0]-base[:,:,0];active=edits[:,:,i,0]>1e-8;changed=edits[:,:,i,3]>1e-8;positive=delta>1e-10;negative=delta< -1e-10;failure_only=np.where(failure[:,:,None],value,base);failure_benefit=np.where((failure&positive)[:,:,None],value,base)
        row=dict(arm=a,actual=detail(value,base,rows),oracle_failure_only=detail(failure_only,base,rows),oracle_failure_and_benefit=detail(failure_benefit,base,rows),
            oracle_all_case_benefit_delta_pdms=float(np.maximum(delta,0).mean()*100),latent_activation=float(active.mean()),policy_change_rate=float(changed.mean()),
            failure_precision_of_policy_change=float((changed&failure).sum()/max(changed.sum(),1)),failure_recall_of_policy_change=float((changed&failure).sum()/max(failure.sum(),1)),
            useful_policy_change_precision=float((changed&positive).sum()/max(changed.sum(),1)),harmful_policy_change_fraction=float((changed&negative).sum()/max(changed.sum(),1)),
            active_relative_median=float(np.median(edits[:,:,i,0][active])) if active.any() else 0.,actual_relative_max=float(edits[:,:,i,0].max()))
        methods.append(row)
        if not a.get('control'):
            use=value[:,:,0]>best[:,:,0];best[use]=value[use]
    return dict(status='PASS',time=stamp(),study='semantic_correction' if semantic else 'primary',contrasts=records,methods=methods,
        actual_base_all_seven_fields_exact=True,baseline_mean_pdms=float(base[:,:,0].mean()*100),sessions=len(names),cases=len(rows),seeds=scores.shape[0],case_noise_unit='One fixed policy; repeated noise draws are averaged inside each case for uncertainty.',
        oracle_all_genuine=detail(best,base,rows,ci=True),oracle_failure_only_genuine=detail(np.where(failure[:,:,None],best,base),base,rows,ci=True),score_sha256=sha(folder/'scores.npy'))


def main():
    setup('vlm_repair/final_statistics');summaries=[]
    if (VOUT/'final/PRIMARY_INFERENCE_COMPLETE.json').exists():summaries.append(comparisons(VOUT/'analysis/final_test',read(VOUT/'final/TEST_LOCK.json')))
    if (SEM/'repair/INFERENCE_COMPLETE.json').exists():summaries.append(comparisons(VOUT/'analysis/final_test_semantic',read(SEM/'repair/TEST_LOCK.json'),True))
    assert summaries,'No complete locked final test to analyze'
    records=[c for s in summaries for c in s['contrasts']]
    for family in {r['family'] for r in records}:
        group=sorted([r for r in records if r['family']==family],key=lambda r:r['p_one_sided']);highest=0.
        for i,r in enumerate(group):highest=max(highest,min(1.,r['p_one_sided']*(len(group)-i)));r['p_holm']=highest
    destination=VOUT/'statistics'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');atomic(destination/'FINAL_STATISTICS.json',dict(status='PASS',time=stamp(),studies=summaries,joint_primary_and_semantic_families=True,
        semantic_complete=bool((SEM/'repair/INFERENCE_COMPLETE.json').exists()),complete_global_task_not_implied=True,interpretation='Infer locked policies only; pooled Oracle bounds are privileged diagnostics, not deployable selectors.'))
    print('VLM_LOCKED_STATISTICS_PASS',len(summaries),str(destination.relative_to(ROOT)))
if __name__=='__main__':main()
