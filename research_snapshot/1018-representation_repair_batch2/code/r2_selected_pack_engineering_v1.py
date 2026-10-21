"""Fresh selected-pack checks against original exploration candidate outcomes."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    from r2_frozen_policy_pack_v2 import run as evaluate
    from r2_point_response import FIELDS
    result=evaluate(engine,task['evaluation'],pool)
    data=read(ROOT/result['path']);records=data['records']
    lookup={(r['token'],r['arm'],r['seed_index']):r for r in records}
    assert len(lookup)==len(records)
    rows=read(ROOT/task['evaluation']['rows']);panel=task['evaluation']['panel']
    pack=read(ROOT/task['evaluation']['pack']);comparisons=0;choices=0
    for source in task['banks']:
        assert sha(ROOT/source['path'])==source['sha256']
        bank=read(ROOT/source['path']);assert bank['heldout_fold']==-1
        assert sha(ROOT/bank['matrix'])==bank['matrix_sha256']
        with np.load(ROOT/bank['matrix']) as z:
            indices=list(z['global_indices']);arms=list(z['arm_ids'])
            trajectories=np.array(z['trajectory']);scores=np.array(z['scores'])
            assert list(z['seeds'])==[0,1,2]
        own=[p for p in pack['policies'] if p['kind']!='Base'
             and read(ROOT/p['policy'])['system']==bank['system']]
        assert own
        part_ids=set()
        for config in own:
            policy=read(ROOT/config['policy'])
            parts=policy['configuration']['model']['parts'] if config['kind'] in ['joint','finite'] else policy['parts']
            part_ids.update(p['id'] for p in parts)
        for index in panel:
            row=rows[index];assert row['subset']=='exploration';position=indices.index(index)
            for part in ['baseline',*sorted(part_ids)]:
                arm=arms.index(part);actual_arm=part if part=='baseline' else 'candidate_'+part
                for noise in [0,1,2]:
                    record=lookup[(row['token'],actual_arm,noise)]
                    assert np.array_equal(np.asarray(record['trajectory'],dtype=np.float32),trajectories[position,arm,noise]),(bank['system'],actual_arm,noise,'trajectory')
                    assert record['score']=={f:float(v) for f,v in zip(FIELDS,scores[position,arm,noise])},(bank['system'],actual_arm,noise,'score')
                    comparisons+=1
    for config in pack['policies']:
        if config['kind'] not in ['finite','candidate']:continue
        policy=read(ROOT/config['policy'])
        parts=policy['configuration']['model']['parts'] if config['kind']=='finite' else policy['parts']
        for index in panel:
            for noise in [0,1,2]:
                record=lookup[(rows[index]['token'],config['id'],noise)]
                choice=record['choice'];assert 0<=choice<=len(parts)
                expected='baseline' if choice==0 else 'candidate_'+parts[choice-1]['id']
                other=lookup[(record['token'],expected,noise)]
                assert record['trajectory']==other['trajectory'] and record['score']==other['score']
                choices+=1
    for record in records:
        assert record['seed']==seed(record['token'],record.get('noise_draw_index',record['seed_index']))
        if record['arm'].startswith('base_resample_'):assert record['noise_draw_index']>=5
    proof=ROOT/'provenance/final_confirmation/SELECTED_PACK_ENGINEERING_PASS.json'
    atomic(proof,dict(status='PASS',time=stamp(),result=result,
        selected_pack_sha256=task['evaluation']['pack_sha256'],
        exact_original_bank_trajectory_and_real_score_comparisons=comparisons,
        deployment_choices_equal_actual_whole_candidates=choices,
        actual_fresh_generation_and_independent_scoring=True,
        validation_accessed=False,test_accessed=False,
        handler_sha256=sha(Path(__file__))))
    return dict(path=str(proof.relative_to(ROOT)),sha256=sha(proof),result=result)
