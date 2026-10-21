"""Separate failure-only capability from gains on already successful outputs; stable cases and compatible pools."""
from common import *
import numpy as np
from repair_oracle_inventory_v2 import category,stats
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
OUT=VOUT/'oracle_extended'

def detail(value,base,rows,ci=False):
    result=stats(value,base);b=base[:,:,0];a=value[:,:,0];failed=b<.7;high=b>.9;sf=failed.all(0);sh=high.all(0)
    result.update(stable_fail_cases=int(sf.sum()),stable_fail_repaired70_any=int((sf&(a>=.7).any(0)).sum()),stable_fail_repaired70_all=int((sf&(a>=.7).all(0)).sum()),
        stable_fail_repaired90_any=int((sf&(a>.9).any(0)).sum()),stable_fail_repaired90_all=int((sf&(a>.9).all(0)).sum()),stable_high_cases=int(sh.sum()),stable_high_damage_any=int((sh&(a<.7).any(0)).sum()),
        baseline_zero_to_above90=int(((b==0)&(a>.9)).sum()),failure_gain_over20points=int((failed&((a-b)>.2)).sum()))
    if ci:
        sessions=np.array([r['session'] for r in rows]);unique,inv=np.unique(sessions,return_inverse=True);delta=(a-b).mean(0);sums=np.bincount(inv,weights=delta);counts=np.bincount(inv);rng=np.random.default_rng(20261016);draw=rng.integers(len(unique),size=(1000,len(unique)))
        result['session_bootstrap_delta_ci95']=np.quantile(sums[draw].sum(1)/counts[draw].sum(1)*100,[.025,.975]).tolist()
    return result

def derive(scores,arms,rows):
    base=np.asarray(scores[:,:,0,:]);failed=base[:,:,0]<.7;records=[];best=base.copy()
    for i,arm in enumerate(arms,1):
        value=np.asarray(scores[:,:,i,:]);positive=value[:,:,0]>base[:,:,0];use=failed&positive
        failure_positive=np.where(use[:,:,None],value,base)
        records.append(dict(id=arm['id'],category=category(arm),internal_gate=arm.get('gate',arm.get('legacy_arm',{}).get('gate','none')),
            external_failure_and_benefit=detail(failure_positive,base,rows),
            failure_only_delta_pdms=float(((value[:,:,0]-base[:,:,0])*failed).mean()*100),all_case_benefit_delta_pdms=float(np.maximum(value[:,:,0]-base[:,:,0],0).mean()*100)))
        if category(arm)=='repair':
            choose=value[:,:,0]>best[:,:,0];best[choose]=value[choose]
    failure_best=np.where(failed[:,:,None],best,base)
    return dict(methods=records,all_genuine_plus_base_oracle=detail(best,base,rows,ci=True),failure_only_genuine_plus_base_oracle=detail(failure_best,base,rows,ci=True))

def main():
    setup('vlm_repair/oracle_extended');panels=[];compatible={}
    for root in ['repair_v1/analysis','candidate_repair_v1/analysis']:
        for p in sorted((ROOT/root).glob('*/scores.npy')):
            folder=p.parent;rows=read(folder/'rows.json');arms=read(folder/'arms.json');scores=np.load(p,mmap_mode='r');result=derive(scores,arms,rows)
            result.update(status='PASS',time=stamp(),panel=str(folder.relative_to(ROOT)),seeds=scores.shape[0],cases=len(rows),scores_sha256=sha(p),scope='Raw evaluated-panel population only; enriched screen means cannot be read as full-population PDMS; Oracle is diagnostic.')
            target=OUT/'panels'/(folder.parent.parent.name+'__'+folder.name+'.json');atomic(target,result);panels.append(dict(panel=result['panel'],path=str(target.relative_to(ROOT))))
            if len(rows) in [17475,12146] and scores.shape[0] in [3,5]:
                key=digest(dict(tokens=[r['token'] for r in rows],seeds=scores.shape[0],baseline_sha=hashlib.sha256(np.asarray(scores[:,:,0,:]).tobytes()).hexdigest()))
                compatible.setdefault(key,[]).append((folder,rows,arms))
            print('PANEL_ORACLE_EXTENDED',result['panel'],flush=True)
    merged=[]
    for key,items in compatible.items():
        source=np.load(items[0][0]/'scores.npy',mmap_mode='r');base=np.asarray(source[:,:,0,:]);rows=items[0][1];best=base.copy();methods=[];fingerprints=set()
        for folder,_,arms in items:
            a=np.load(folder/'scores.npy',mmap_mode='r');assert np.array_equal(base,a[:,:,0,:])
            for i,arm in enumerate(arms,1):
                if category(arm)!='repair':continue
                value=np.asarray(a[:,:,i,:]);fingerprint=hashlib.sha256(value.tobytes()).hexdigest();methods.append(dict(id=arm['id'],panel=str(folder.relative_to(ROOT)),score_functional_duplicate=fingerprint in fingerprints));fingerprints.add(fingerprint)
                use=value[:,:,0]>best[:,:,0];best[use]=value[use]
        f=base[:,:,0]<.7;failure=np.where(f[:,:,None],best,base)
        merged.append(dict(id=key,panels=[str(x[0].relative_to(ROOT)) for x in items],cases=len(rows),seeds=base.shape[0],method_instances=len(methods),distinct_score_functions=len(fingerprints),methods=methods,
            all_case_oracle=detail(best,base,rows,ci=True),failure_only_oracle=detail(failure,base,rows,ci=True),baseline_all_fields_exact=True,
            caveat='Only exact same token ordering, seed count and bit-exact seven-field Base can merge. Score-identical methods are equivalent for this Oracle only; their trajectories need not match.'))
    atomic(OUT/'INDEX.json',dict(status='PASS',time=stamp(),panels=panels,compatible_merged_pools=merged,all_evaluated_method_failure_benefit_bounds=True,case_and_noise_units_distinct=True,
        caveat='Existing internal gates are retained unless an actually computed ungated counterpart is explicitly included. No new VLM selection uses old test Oracle results.'))
    print('ORACLE_EXTENDED_ALL_PANELS_PASS',len(panels),flush=True)
if __name__=='__main__':main()
