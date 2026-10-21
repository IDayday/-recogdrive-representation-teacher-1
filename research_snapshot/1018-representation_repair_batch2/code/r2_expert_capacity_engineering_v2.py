"""Reuse accepted smoke weights; test raw/cache on explicit exploration cases."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    import r2_learned_eval as raw
    import r2_expert_capacity_eval_cached as cached
    protocol=read(ROOT/task['protocol']);assert sha(ROOT/task['protocol'])==task['protocol_sha256'];models=[];pairs=[]
    for block in protocol['sites']:
        for rank in protocol['ranks']:
            p=ROOT/'expert_capacity_controls/models'/f'capacity_engineering_{block}_r{rank}'/'TRAINING.json';d=read(p);assert d['task']['rank']==rank and d['task']['steps']==8 and d['task']['heldout_fold']==0 and d['base_weights_frozen'];ck=d['checkpoints'][0];assert sha(ROOT/ck['path'])==ck['sha256']
            with np.load(ROOT/ck['path']) as z:assert np.any(z['up.weight']!=0) and all(np.isfinite(z[k]).all() for k in z.files)
            models.append(d)
            if rank==32:
                ref=ROOT/'learned_experts'/('capacity_reference_'+block)/'TRAINING.json';a=read(ref)
                with np.load(ROOT/a['checkpoints'][0]['path']) as za,np.load(ROOT/ck['path']) as zb:assert za.files==zb.files and all(np.array_equal(za[k],zb[k]) for k in za.files)
                assert a['records']==d['records'];pairs.append(dict(block=block,reference=str(ref.relative_to(ROOT)),controlled=str(p.relative_to(ROOT)),weights_and_trace_bitwise_equal=True))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);eligible=[i for i,r in enumerate(rows) if r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=0];panel=[next(i for i in eligible if quality[i]<.7),next(i for i in eligible if quality[i]>.9)];arms=[]
    for m in models:
        for strength in [.5,1.]:
            spec=dict(training_task=m['task'],checkpoint=m['checkpoints'][0],strength=strength);arms.append(dict(id='capacity_smoke_arm_'+digest(spec)[:20],kind='learned',slot=0,**spec))
    stage=ROOT/'runs/expert_capacity_eval_engineering_v2';outputs=[]
    for name,module in [('raw',raw),('cached',cached)]:
        point=stage/'points'/(name+'.json');assert not point.exists();atomic(point,dict(id=name,panel=panel,seeds=[0,1,2],arms=arms,training_only=True));t=dict(id='capacity_eval_v2_'+name,stage=str(stage.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=0,end=2);outputs.append(module.run(engine,t,pool))
    a=read(ROOT/outputs[0]['path']);b=read(ROOT/outputs[1]['path']);assert a['records']==b['records'] and len(a['records'])==78
    path=ROOT/'provenance/EXPERT_CAPACITY_CONTROL_ENGINEERING_PASS.json';assert not path.exists();atomic(path,dict(status='PASS_EXACT_MATCHED_TRAINING_AND_RAW_CACHED_EVALUATION',time=stamp(),protocol=task['protocol'],protocol_sha256=task['protocol_sha256'],rank32_original_training_vs_namespace_copy=pairs,all_ranks_sites_nonzero_trained=True,eval_reference=outputs[0],eval_cached=outputs[1],actual_complete_records_per_runtime=78,actual_seed_trajectory_score_and_relative_edit_exact=True,raw_and_cached_eval_seconds=[a['seconds'],b['seconds']],single_short_timing_not_sustained_speedup=True,engineering_cases=[dict(index=i,token=rows[i]['token'],subset=rows[i]['subset'],excluded_outer_fold=0) for i in panel],v1_failed_before_raw_input_read='runs/discovery_v1/failures_gpu/dispatch_expert_capacity_engineering_v1.json',completed_smoke_weights_reused_not_overwritten=True,validation_accessed=False,test_accessed=False,not_deployment_or_science_gain=True));return dict(path=str(path.relative_to(ROOT)))
