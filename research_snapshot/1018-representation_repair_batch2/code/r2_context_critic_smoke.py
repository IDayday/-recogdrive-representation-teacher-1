"""Feature-readout acceptance, exact compatibility and original score reuse."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    import torch
    from worker import load_features
    from r2_context_critic import run as train,load,inner_session
    from r2_context_predict import run as predict
    from r2_native_training_ab import equal_arrays
    from repair_score import score_group
    config=read(ROOT/'runs/token_critic_pilot_v1/tasks.json')[0]
    reference=read(ROOT/'token_critic_prefetch_v2/token_prefetch_ab_v2/TRAINING.json')
    compat=train(engine,dict(config,id='context_post_valid_compatibility_v1',context_view='post_valid'),pool);compatibility=equal_arrays(reference,read(ROOT/compat['path']))
    response_path=config['responses'][0];response=read(ROOT/response_path);bank=read(ROOT/response['point']);rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    with np.load(ROOT/response['matrix']) as z:indices=np.array(z['global_indices']);scores=np.array(z['scores']);trajectory=np.array(z['trajectory']);arm_ids=list(z['arm_ids']);seeds=np.array(z['seeds'])
    j=next(j for j,i in enumerate(indices) if inner_session(rows[int(i)]['session']));index=int(indices[j]);parts={p['id']:p for p in bank['arms']}
    ordered=[parts[v] for _,v in sorted(bank['policies']['PDMS'].items(),key=lambda p:int(p[0]))];pick=[0]+[arm_ids.index(p['id']) for p in ordered]
    reports=[]
    for view in ['pre_valid','post_all','pre_all']:
        result=train(engine,dict(config,id='context_'+view+'_engineering_v1',context_view=view),pool);model=read(ROOT/result['path']);ck=model['checkpoints'][-1]
        assert load(ck['path'],ck['sha256']).context.in_features==(1536 if view.startswith('pre') else 384)
        point=ROOT/task['stage']/'points'/(view+'.json')
        atomic(point,dict(id='context_'+view+'_engineering',mode='calibration',heldout_fold=-1,system=bank['system'],parts=ordered,items=[[response_path,j]],responses=[response_path],
            critics=[dict(id=view,checkpoint=ck,heldout_fold=-1,context_view=view)]))
        predicted=predict(engine,dict(id=task['id']+'_'+view,stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=1),pool)
        with np.load(ROOT/predicted['matrix']) as z:
            assert np.array_equal(z['scores'],scores[j,pick].transpose(1,0,2));assert np.array_equal(z['trajectory'],trajectory[j,pick].transpose(1,0,2,3));assert np.isfinite(z['predicted']).all()
        reports.append(dict(view=view,checkpoint=ck,prediction=predicted,actual_unchanged_scores_exact=True))
    # Independent scorer check on a real frozen candidate, rather than treating
    # a learned score prediction as the true metric.
    record=score_group(dict(metric_cache=rows[index]['metric_cache'],metric_sha256=__import__('repair_engine').baseline_row(rows[index])['metric_sha256'],scoring=engine.cfg['scoring'],records=[dict(trajectory=trajectory[j,pick[-1],0].tolist())]))[0]
    fields=read(ROOT/response_path)['fields'];assert np.array_equal(np.asarray([record['score'][f] for f in fields]),scores[j,pick[-1],0])
    engine.verify_engine();path=ROOT/'provenance/CONTEXT_CRITIC_ENGINEERING_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),compatibility_post_valid_all_parameters_exact=compatibility,variants=reports,
        candidate_trajectory_and_actual_score_unchanged=True,independent_rescore_exact=True,Base_frozen=True,
        scope='Feature sufficiency control; labels and optimization schedule matched. Different view is a scientific variant, not a runtime optimization.'))
    return dict(path=str(path.relative_to(ROOT)),variants=3)
