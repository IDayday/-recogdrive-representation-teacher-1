"""CPU-only ensembles of actual matched continuation predictions.

Original full/uniform producers bind readout seed to expert-bank seed: their
three cross-readout predictions on one bank do not exist. Use the completed
largeH same-bank continuation control instead; report shared warm initialization.
"""
from r2_common import *
from r2_resume_support import append_once
import re


def available():
    stage=ROOT/'runs/large_success_critic_held_v1';receipts={p.stem for p in (stage/'receipts').glob('*.json')};groups={}
    for path in (stage/'points').glob('*.json'):
        d=read(path);m=re.fullmatch(r'(representation_K2_seed0__largeH_(original|augmented)_total(16000|32000)_(post_valid|pre_all))_fit(202610180[123])',d['system'])
        if m is None or d['mode']!='heldout' or d['heldout_fold']!=0:continue
        if not all(d['id']+'_%04d'%j in receipts for j in range(0,len(d['items']),8)):continue
        policy=read(ROOT/d['policy']);key=(m[1],d['heldout_fold'],d['role'],m[4]);groups.setdefault(key,{})[d['fit_seed']]=dict(policy=d['policy'],policy_sha256=d['policy_sha256'],held_point=str(path.relative_to(ROOT)),held_stage=str(stage.relative_to(ROOT)),calibration_stage=str(Path(policy['source_point']).parent.parent))
    output=[]
    for key,members in sorted(groups.items()):
        if set(members)!={2026101801,2026101802,2026101803}:continue
        output.append(dict(system=key[0],heldout_fold=key[1],role=key[2],context=key[3],source_kind='largeH_'+key[3],members=[members[j] for j in sorted(members)]))
    return output


def main():
    protocol='config/CRITIC_ENSEMBLE_AVAILABLE_DATA_PROTOCOL_V2.json';hashed=sha(ROOT/protocol);handler='code/r2_critic_ensemble.py';version=sha(ROOT/handler);proof=ROOT/'provenance/CRITIC_ENSEMBLE_AVAILABLE_DATA_ENGINEERING_PASS.json'
    if not proof.exists():
        choices=[]
        while not choices:choices=available();time.sleep(30) if not choices else None
        spec=dict(**choices[0],protocol=protocol,protocol_sha256=hashed,engineering=True);ident='outcome_ensemble_available_engineering_'+digest(spec)[:24];task=dict(id=ident,handler=handler,handler_sha256=version,**spec);append_once('cpu',[task])
        receipt=RUN/'receipts_cpu'/(ident+'.json')
        while not receipt.exists():time.sleep(30)
        r=read(receipt);report=read(ROOT/r['result']['path']);assert report['new_model_or_trajectory_or_scoring_runs']==0 and report['zero_identity_and_single_member_rule_checked'] and len(report['outputs'])==3
        for out in report['outputs']:
            d=read(ROOT/out['path']);assert '/critic_ensemble_engineering/' in out['path'];p=read(ROOT/out['policy']);assert p['zero_expert_exact'] and p['no_hidden_or_trajectory_linear_mix'] and p['heldout_fold']==spec['heldout_fold'];assert len(p['members'])==3
        atomic(proof,dict(status='PASS_ACTUAL_STORED_PREDICTION_ENGINEERING',time=stamp(),task=task,receipt=str(receipt.relative_to(ROOT)),summary=r['result']['path'],zero_identity_and_previous_single_member_choices_exact=True,three_methods_actual_complete_candidate_scoring_reused=True,selected_before_held_score_access=True,engineering_projection_separate_from_scientific_CV=True,new_GPU_model_or_trajectory_or_scoring=0))
    known=set()
    while True:
        work=[];ready=available()
        for item in ready:
            spec=dict(**item,protocol=protocol,protocol_sha256=hashed);ident='outcome_available_critic_ensemble_'+digest(spec)[:24]
            if ident in known:continue
            work.append(dict(id=ident,handler=handler,handler_sha256=version,**spec));known.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/critic_ensembles/AVAILABLE_DATA_PRODUCER.json',dict(time=stamp(),ready_three_fit_groups=len(ready),queued=len(known),CPU_only=True,all_calibration_parameters_predeclared=True));time.sleep(120)


if __name__=='__main__':main()
