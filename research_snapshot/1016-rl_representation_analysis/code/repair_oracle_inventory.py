"""Privileged diagnostic bounds for every actually scored panel; no model or test tuning."""
from common import *
import numpy as np
from repair_queue_v2 import atomic_unique as atomic

OUT=ROOT/'vlm_repair_v1/legacy_oracle'

def stats(values,base):
    pd=values[:,:,0];bp=base[:,:,0];failure=bp<.7;high=bp>.9;delta=pd-bp
    result=dict(mean_pdms=float(pd.mean()*100),delta_pdms=float(delta.mean()*100),per_seed_delta_pdms=(delta.mean(1)*100).tolist(),outputs=int(pd.size),failure_outputs=int(failure.sum()),
        changed_outputs=int(np.count_nonzero(np.any(values!=base,axis=2))),improved_outputs=int((delta>1e-10).sum()),worsened_outputs=int((delta< -1e-10).sum()),
        repaired_to70=int((failure&(pd>=.7)).sum()),repaired_above90=int((failure&(pd>.9)).sum()),high_to_failure=int((high&(pd<.7)).sum()),high_to_not_high=int((high&(pd<=.9)).sum()),
        failure_delta_pdms=float(delta[failure].mean()*100) if failure.any() else None,
        delta_failure_count=int((pd<.7).sum()-failure.sum()),delta_zero_count=int((pd<=1e-10).sum()-(bp<=1e-10).sum()))
    for name,index in [('collision',1),('offroad',2),('ttc',4)]:
        fail=values[:,:,index]<1-1e-7;bfail=base[:,:,index]<1-1e-7
        result.update({name+'_new':int((fail&~bfail).sum()),name+'_removed':int((~fail&bfail).sum()),name+'_net':int(fail.sum()-bfail.sum())})
    return result

def category(arm):
    m=arm.get('method','');legacy=arm.get('legacy_arm',{})
    if m=='legacy':m=legacy.get('method','')
    if m.startswith('patch'):return 'privileged_reference_patch'
    if m in ['random','random_subspace','reverse','random_direction','haar'] or arm.get('space')=='random':return 'null_control'
    return 'repair'

def panel(path):
    scores=np.load(path/'scores.npy',mmap_mode='r');arms=read(path/'arms.json');rows=read(path/'rows.json');assert scores.shape[2]==len(arms)+1 and scores.shape[1]==len(rows)
    base=np.asarray(scores[:,:,0,:]);output=[];keepers=[];excluded=[]
    for i,arm in enumerate(arms,1):
        value=np.asarray(scores[:,:,i,:]);label=category(arm)
        failure_gate=np.where((base[:,:,0]<.7)[:,:,None],value,base);benefit=np.where((value[:,:,0]>base[:,:,0])[:,:,None],value,base)
        output.append(dict(id=arm['id'],category=label,arm=arm,executed_internal_gate=arm.get('gate',arm.get('legacy_arm',{}).get('gate','none')),
            unconditional_as_executed=stats(value,base),oracle_base_failure_only=stats(failure_gate,base),oracle_only_if_pdms_improves=stats(benefit,base)))
        (keepers if label=='repair' else excluded).append(i)
    def oracle(indices):
        best=base.copy();choice=np.zeros(base.shape[:2],dtype=np.int32)
        for i in indices:
            v=np.asarray(scores[:,:,i,:]);use=v[:,:,0]>best[:,:,0];best[use]=v[use];choice[use]=i
        return dict(summary=stats(best,base),selected_arm_counts={('baseline' if i==0 else arms[i-1]['id']):int((choice==i).sum()) for i in np.unique(choice)},base_included=True,strict_pdms_ties_keep_base_or_first=True)
    result=dict(status='COMPLETE',time=stamp(),panel=str(path.relative_to(ROOT)),scenes=len(rows),seeds=scores.shape[0],arms=len(arms),source_scores_sha256=sha(path/'scores.npy'),source_arms_sha256=sha(path/'arms.json'),source_rows_sha256=sha(path/'rows.json'),
        scope='This panel only, identical scene ordering and seeds. Oracle is diagnostic, not deployable performance.',
        gating_warning='External Oracle does not bypass an existing internal gate. Ungated arms are identified separately; do not interpret a gated Oracle as the ungated operator limit.',
        methods=output,repair_candidates_plus_base_oracle=oracle(keepers),all_computed_including_null_and_privileged_reference_oracle=oracle(keepers+excluded),excluded_from_main=[dict(id=arms[i-1]['id'],category=category(arms[i-1])) for i in excluded])
    dest=OUT/(path.parent.parent.name+'__'+path.name+'.json');atomic(dest,result)
    return {k:result[k] for k in ['panel','scenes','seeds','arms','repair_candidates_plus_base_oracle']}

def main():
    setup('vlm_repair/legacy_oracle');results=[]
    for source in ['repair_v1/analysis','candidate_repair_v1/analysis']:
        for p in sorted((ROOT/source).glob('*/scores.npy')):
            result=panel(p.parent);results.append(result);print(json.dumps({k:result[k] for k in ['panel','scenes','seeds','arms']}),flush=True)
    atomic(OUT/'INVENTORY.json',dict(status='PASS',time=stamp(),panels=results,all_actual_panels_covered=True,no_model_rerun=True,incompatible_panels_never_merged=True,all_methods_external_gate_not_internal_bypass=True,interpretation='Paired-seed output counts; scenes may repeat across noise seeds. No inference that this diagnostic is a deployable selector.'))
if __name__=='__main__':main()
