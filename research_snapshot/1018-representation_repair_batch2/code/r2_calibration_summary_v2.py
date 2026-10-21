"""Real-outcome calibration summaries, clearly separating privileged selection."""
from r2_common import *


def run(task):
    import numpy as np
    training=read(ROOT/'runs/learned_calibration_v1/tasks.json')
    folder=ROOT/'analysis/responses/learned_calibration_eval_v1';began=time.monotonic()
    while not all((folder/(t['id']+'.json')).exists() for t in training):
        assert time.monotonic()-began<7200,'Calibration compact response reduction stalled'
        atomic(ROOT/'analysis/learned_calibration/SUMMARY_WAIT.json',dict(time=stamp(),ready=len(list(folder.glob('*.json'))),expected=len(training)))
        time.sleep(30)
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);records=[];score_banks=[];bank_labels=[];reference=None
    for t in training:
        response=read(folder/(t['id']+'.json'));descriptor=read(ROOT/response['point'])
        with np.load(ROOT/response['matrix']) as z:
            scores=np.array(z['scores']);indices=np.array(z['global_indices']);arm_ids=list(z['arm_ids'])
        if reference is None:
            reference=scores[:,0];panel=indices;native_quality=quality[indices]
        else:assert np.array_equal(reference,scores[:,0]) and np.array_equal(panel,indices)
        masks=dict(failure=native_quality<.7,high=native_quality>.9,intermediate=(native_quality>=.7)&(native_quality<=.9))
        arms={a['id']:a for a in descriptor['arms']}
        for a,ident in enumerate(arm_ids[1:],1):
            arm=arms[ident];groups={}
            for group,mask in masks.items():
                base=scores[mask,0];after=scores[mask,a];delta=after-base
                groups[group]=dict(cases=int(mask.sum()),gain_each_noise=(delta[:,:,0].mean(0)*100).tolist(),
                      base_each_noise=(base[:,:,0].mean(0)*100).tolist(),after_each_noise=(after[:,:,0].mean(0)*100).tolist(),
                      net_collision_each_noise=(np.sum(after[:,:,1]<1,0)-np.sum(base[:,:,1]<1,0)).tolist(),
                      net_offroad_each_noise=(np.sum(after[:,:,2]<1,0)-np.sum(base[:,:,2]<1,0)).tolist(),
                      net_zero_each_noise=(np.sum(after[:,:,0]==0,0)-np.sum(base[:,:,0]==0,0)).tolist(),
                      high_damaged_each_noise=np.sum((base[:,:,0]>.9)&(after[:,:,0]<=.9),0).tolist())
            records.append(dict(training_id=t['id'],block=t['block'],space=t['space_control'],basis=read((ROOT/t['fit_path']).with_suffix('.json'))['config'],
                   cap=t['cap'],rank=t['rank'],step=arm['checkpoint']['step'],strength=arm['strength'],arm=ident,groups=groups))
            if arm['strength']>0:
                score_banks.append(scores[:,a]);bank_labels.append(dict(training_id=t['id'],arm=ident))
    bank=np.stack([reference]+score_banks,1);labels=[dict(arm='baseline')]+bank_labels
    selection=bank[:,:,0,0].argmax(1);fixed=bank[np.arange(len(panel)),selection]
    per_draw=np.stack([bank[np.arange(len(panel)),bank[:,:,j,0].argmax(1),j] for j in range(reference.shape[1])],1)
    oracle={}
    for group,mask in masks.items():
        oracle[group]=dict(cases=int(mask.sum()),fixed_S0_selection_gain_each_noise=((fixed[mask,:,0]-reference[mask,:,0]).mean(0)*100).tolist(),
             per_draw_reselection_gain_each_noise=((per_draw[mask,:,0]-reference[mask,:,0]).mean(0)*100).tolist(),
             choices=[labels[int(i)] for i in selection[mask]])
    result=dict(status='COMPLETE',time=stamp(),training_configurations=len(training),records=records,
                privileged_library_oracle=oracle,cases=len(panel),source_panel=panel.tolist(),
                training_only=True,heldout_confirmation=False,population_gain_claim=False,
                selection_note='Calibration on enriched exploration panel; report actual cohorts. Keep full grid for proper CV.',
                oracle_note='S0 fixed scene choices and per-draw re-selection are distinct privileged diagnostics, Base included.')
    path=ROOT/'analysis/learned_calibration/SUMMARY.json';atomic(path,result)
    return dict(path=str(path.relative_to(ROOT)),configurations=len(training),evaluated_arms=len(records),oracle=oracle)
