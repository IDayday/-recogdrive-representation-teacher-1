"""Fresh v2 exact primary replay plus actual resampling/finite-route controls."""
from r2_common import *


def run(engine,task,pool):
    from r2_frozen_policy_pack_v2 import run as evaluate
    result=evaluate(engine,task['evaluation'],pool);new=read(ROOT/result['path'])['records'];old=read(ROOT/task['reference_result'])['records'];lookup={(r['arm'],r['token'],r['seed_index']):r for r in new}
    for r in old:
        other=lookup[(r['arm'],r['token'],r['seed_index'])];assert r['trajectory']==other['trajectory'] and r['score']==other['score']
    pack=read(ROOT/task['evaluation']['pack']);policies={p['id']:p for p in pack['policies']};count=0
    for r in new:
        if r['arm'] not in policies or policies[r['arm']]['kind']!='finite':continue
        p=read(ROOT/policies[r['arm']]['policy']);parts=p['configuration']['model']['parts'];expected='baseline' if r['choice']==0 else 'candidate_'+parts[r['choice']-1]['id'];ref=lookup[(expected,r['token'],r['seed_index'])]
        assert r['trajectory']==ref['trajectory'] and r['score']==ref['score'];count+=1
    extra=[r for r in new if r['arm'].startswith('base_resample_')];assert len(extra)==len(task['evaluation']['panel'])*len(task['evaluation']['seeds'])*pack['base_resampling_extra_candidates']
    for r in extra:
        assert r['seed']==seed(r['token'],r['noise_draw_index']) and r['noise_draw_index']>=5
    proof=ROOT/'provenance/FROZEN_POLICY_PACK_V2_ENGINEERING_PASS.json';atomic(proof,dict(status='PASS',time=stamp(),result=result,old_primary_records_exact=len(old),finite_actual_whole_candidate_choices_exact=count,actual_resampling_outputs=len(extra),reference_source=task['reference_result'],fresh_actual_generation_and_scoring=True,formal_validation_or_test_not_accessed=True));return dict(path=str(proof.relative_to(ROOT)))
