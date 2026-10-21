"""Actual frozen-critic M1 versus shared-read M2, exact arrays across four views."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    from r2_context_predict import run as context
    from r2_state_condition_predict import run as state
    from r2_prediction_batch import run as batch
    comparisons=[];timings=[]
    for g,group in enumerate(task['groups']):
        refs=[];entries=[];point=group['point'];handler=group['handler'];predict=state if handler.endswith('state_condition_predict.py') else context
        for j,critic in enumerate(group['critics']):
            refbase=ROOT/task['stage']/'references';refpoint=refbase/'points'/('g%d_c%d.json'%(g,j));atomic(refpoint,dict(point,id='ref_g%d_c%d'%(g,j),critics=[critic]));ref_task=dict(id='ref_g%d_c%d'%(g,j),stage=str(refbase.relative_to(ROOT)),point=str(refpoint.relative_to(ROOT)),start=0,end=len(point['items']));refs.append(predict(engine,ref_task,pool))
            base=ROOT/task['stage']/'isolated_sources';path=base/'points'/('g%d_c%d.json'%(g,j));atomic(path,dict(point,id='candidate_g%d_c%d'%(g,j),critics=[critic]));canonical=dict(id='candidate_g%d_c%d'%(g,j),stage=str(base.relative_to(ROOT)),point=str(path.relative_to(ROOT)),start=0,end=len(point['items']));entries.append(dict(stage=str(base.relative_to(ROOT)),task=canonical,handler=handler,handler_sha256=sha(ROOT/handler)))
        physical=batch(engine,dict(id='engineering_batch_g'+str(g),stage=task['stage'],entries=entries),pool)
        for j,(reference,entry) in enumerate(zip(refs,entries)):
            refmeta=read(ROOT/reference['path']);path=ROOT/entry['stage']/'results'/(entry['task']['id']+'.npz')
            with np.load(ROOT/refmeta['path']) as a,np.load(path) as b:
                assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files),(g,j)
            comparisons.append(dict(view=group['view'],critic=j,arrays_exact=True,reference_sha256=refmeta['sha256'],projected_sha256=sha(path)))
        timings.append(dict(view=group['view'],single_sum_seconds=sum(read(ROOT/r['path'])['seconds'] for r in refs),shared_physical_seconds=physical['seconds'],cases=len(point['items']),critics=len(group['critics'])))
    path=ROOT/'provenance/CRITIC_SHARED_INPUT_BATCH_ENGINEERING_PASS.json';atomic(path,dict(status='PASS',time=stamp(),comparisons=comparisons,timings=timings,actual_models_and_current_features=True,true_scores_and_trajectories_bitwise_equal=True,all_prediction_columns_bitwise_equal=True,
        modes=['post_valid','pre_all','post_valid_state','post_valid_zero'],timing_limit='Small sequential A/B with warmup/order effects, not a whole-job speedup claim.',production_adoption_pending=True));return dict(path=str(path.relative_to(ROOT)))
