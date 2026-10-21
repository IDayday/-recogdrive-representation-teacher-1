"""Lock two user-requested priorities on full development validation, never on final test."""
from common import *
import numpy as np
from repair_analysis import summarize,safety

STAGES=['validation_repair','validation_preservation','validation_extra','validation_matched','validation_high_pdms']

def main():
    setup('repair/final_selection');compatibility()
    root=ROOT/'repair_v1';base=ROOT/'runs'/read(root/'ACTIVE_RUN.json')['run']
    lock=root/'TEST_LOCK.json';assert not lock.exists(),'Frozen test selection must not be changed'
    rule=read(root/'FINAL_SELECTION_RULE.json');pool={};baselines=None;tokens=None;proofs={}
    for name in STAGES+['postprocess_validation']:
        folder=root/'analysis'/name
        if name!='postprocess_validation' and not (folder/'SUMMARY.json').exists():summarize(base,name)
        result=read(folder/'SUMMARY.json');assert result['coverage_exact']
        safe=safety(name);by_safe={r['arm_id']:r for r in safe['records']}
        matrix=np.load(folder/'scores.npy',mmap_mode='r');rows=read(folder/'rows.json')
        if baselines is None:baselines=np.array(matrix[:,:,0]);tokens=[r['token'] for r in rows]
        else:
            assert tokens==[r['token'] for r in rows]
            assert np.array_equal(baselines,matrix[:,:,0]),name
        proofs[name]=dict(summary_sha256=sha(folder/'SUMMARY.json'),safety_sha256=sha(folder/'SAFETY.json'),matrix_sha256=sha(folder/'scores.npy'))
        for r in result['summaries']:
            a=r['arm']
            if a['method'] in ['random','random_subspace','reverse'] or a.get('privileged_diagnostic') or a.get('control'):continue
            values=by_safe[a['id']]['by_seed'];net={kind:sum(v[kind]['net'] for v in values) for kind in ['collision','offroad','zero']}
            positive=sum(max(n,0) for n in net.values())
            entry=dict(stage=name,summary=r,safety=by_safe[a['id']],net=net,
                safety_eligible=r['mean_delta_pdms']>=0 and all(v<=0 for v in net.values()),added_safety_events=positive)
            if a['id'] in pool:assert pool[a['id']]['summary']==r
            else:pool[a['id']]=entry
    repairs=[r for r in pool.values() if r['summary']['arm']['method']!='trajectory_scale']
    assert repairs
    pdms=max(repairs,key=lambda r:r['summary']['mean_delta_pdms'])
    eligible=[r for r in repairs if r['safety_eligible']]
    safe=max(eligible,key=lambda r:r['summary']['mean_delta_pdms']) if eligible else min(repairs,key=lambda r:(
        r['added_safety_events'],r['net']['collision'],r['net']['offroad'],r['net']['zero'],
        sum(s['high_to_failure'] for s in r['summary']['by_seed']),-r['summary']['mean_delta_pdms']))
    controls=[r for r in pool.values() if r['summary']['arm']['method']=='trajectory_scale'];assert controls
    action=max(controls,key=lambda r:r['summary']['mean_delta_pdms'])
    safe_controls=[r for r in controls if r['safety_eligible']]
    action_safe=max(safe_controls,key=lambda r:r['summary']['mean_delta_pdms']) if safe_controls else min(controls,key=lambda r:(
        r['added_safety_events'],r['net']['collision'],r['net']['offroad'],r['net']['zero'],-r['summary']['mean_delta_pdms']))
    choices=dict(safety_priority=safe,pdms_priority=pdms,action_control=action,action_safety_control=action_safe);arms=[]
    for role,entry in choices.items():
        a=dict(entry['summary']['arm'])
        if a['method']=='trajectory_scale':a['cap']=0.
        if a['id'] not in {v['id'] for v in arms}:arms.append(a)
    arm_path=root/'final_test_arms.json';assert not arm_path.exists();atomic(arm_path,arms)
    fits={str(p.relative_to(ROOT)):sha(p) for p in sorted((root/'fits').glob('*')) if p.suffix in ['.npz','.json']}
    gates={str(p.relative_to(ROOT)):sha(p) for p in sorted((root/'gates').glob('*')) if p.is_file()}
    frozen=dict(status='LOCKED_BEFORE_TEST_ACCESS',time=stamp(),rule=rule,choices=choices,arms=arms,
        eligible_repairs=len(eligible),all_development_candidates=list(pool.values()),source_run=base.name,
        validation_proofs=proofs,arms_sha256=sha(arm_path),fit_sha256=fits,gate_sha256=gates,
        test_access_before_lock=False,test_seeds=rule['test_seeds'],base='fresh frozen RL with exactly matched per-case noise',
        interpretation='Safety eligibility is an observed development criterion, not a safety guarantee; fallback explicitly diagnostic.')
    atomic(lock,frozen)
    print(json.dumps(dict(status=frozen['status'],choices={role:dict(id=v['summary']['arm']['id'],delta=v['summary']['mean_delta_pdms'],net=v['net']) for role,v in choices.items()})),flush=True)

if __name__=='__main__':main()
