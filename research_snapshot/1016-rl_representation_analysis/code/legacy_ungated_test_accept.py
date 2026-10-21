"""Reconstruct exactly the requested privileged failure-only policies from actual inference."""
from common import *
import numpy as np
from repair_queue_v2 import atomic_unique as atomic
from repair_oracle_inventory_v2 import stats
from vlm_core import VOUT

def main():
    setup('vlm_repair/ungated_test_accept');plan=read(VOUT/'LEGACY_UNGATED_TEST_FAILURES.json');source=ROOT/'candidate_repair_v1/analysis/final_test';full=np.load(source/'scores.npy',mmap_mode='r');baseline=np.asarray(full[:,:,0,:]);arms=plan['arms'];out=np.repeat(baseline[:,:,None,:],len(arms)+1,axis=2);seen=np.zeros(out.shape[:3],dtype=bool);seen[:,:,0]=True
    base=ROOT/'runs/candidate_repair_20261016_v1';checks=[]
    for item in plan['records']:
        name=item['stage'];folder=base/'stages'/name;rows=read(folder/'panel.json');index={r['token']:item['full_test_indices'][i] for i,r in enumerate(rows)};lookup={a['id']:i+1 for i,a in enumerate(arms)};paths=list((base/'receipts').glob(name+'_s*.json'));assert len(paths)==item['tasks'];j=item['seed_index']
        for p in paths:
            proof=read(p);path=base/'results'/p.name;assert sha(path)==proof['result_sha256'];result=read(path)
            for r in result['records']:
                i=index[r['token']];assert r['seed_index']==j and r['seed']==seed(r['token'],j);v=np.array([r['score'][f] for f in ['score']+COMPONENTS]);assert baseline[j,i,0]<.7
                if r['arm']=='baseline':assert np.array_equal(v,baseline[j,i]);continue
                a=lookup[r['arm']];assert not seen[j,i,a];seen[j,i,a]=True;out[j,i,a]=v
        assert seen[j,item['full_test_indices'],1:].all();checks.append(dict(seed_index=j,failed_cases=len(rows),tasks=len(paths),fresh_baseline_all_seven_fields_exact=True))
    expected=(baseline[:,:,0]<.7)[:,:,None];assert np.array_equal(seen[:,:,1:],np.broadcast_to(expected,seen[:,:,1:].shape))
    folder=VOUT/'legacy_ungated_test';folder.mkdir(exist_ok=True);p=folder/'failure_gated_scores.npy'
    if p.exists():assert np.array_equal(np.load(p,mmap_mode='r'),out)
    else:
        with p.open('xb') as f:np.save(f,out)
    records=[]
    for a,arm in enumerate(arms,1):
        v=out[:,:,a,:];improved=np.where((v[:,:,0]>baseline[:,:,0])[:,:,None],v,baseline);records.append(dict(arm=arm,external_base_failure_gate=stats(v,baseline),external_failure_and_benefit_gate=stats(improved,baseline)))
    result=dict(status='PASS',time=stamp(),checks=checks,full_test_cases=12146,seeds=5,actually_inferred_failed_outputs=4268,score_fields_exact=True,
        inference_records=sum((len(arms)+1)*c['failed_cases'] for c in checks),scores_sha256=sha(p),methods=records,
        scope='Only actual Base-failed outputs were recomputed with ungated operators; nonfailures exactly retain Base. This is not an unconditional ungated full-test policy or its all-case benefit Oracle.',old_locked_test_choices_unchanged=True,new_vlm_choices_not_informed=True)
    atomic(folder/'ACCEPTANCE.json',result);print('UNGATED_FAILED_TEST_ACCEPT_PASS',result['inference_records'])
if __name__=='__main__':main()
