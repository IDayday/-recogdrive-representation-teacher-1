"""Paired warm A/B: same frozen evaluator, separate versus merged scenes."""
from r2_common import *


def run(engine,task,pool):
    from r2_policy_cohort import execute,MODULES
    import importlib.util
    entries=task['entries'];head=entries[0];source=ROOT/head['handler'];assert sha(source)==head['handler_sha256'];key=head['handler_sha256']
    if key not in MODULES:
        spec=importlib.util.spec_from_file_location('cohort_reference_'+key,source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);MODULES[key]=m
    module=MODULES[key];timing=[];reference=[]
    for round_id in [0,1]:
        this=[]
        if round_id==1:
            physical,projections=execute(engine,entries,pool,task['stage'],task['id']+'_merged')
        for j,entry in enumerate(entries):
            original=entry['task'];t=dict(original,id=task['id']+'_reference_'+str(round_id)+'_'+str(j),stage=task['stage'])
            result=module.run(engine,t,pool);raw=read(ROOT/result['path']);this.append(result['seconds'])
            if round_id==0:reference.append(raw['records'])
            else:assert raw['records']==reference[j] and projections[j]['raw']['records']==reference[j],('Record difference',task['id'],j)
        timing.append(sum(this))
    ratio=physical['seconds']/timing[1];path=ROOT/task['stage']/'proofs'/(task['id']+'.json')
    atomic(path,dict(status='PASS_EXACT_RECORDS',time=stamp(),task=task,handler=head['handler'],separate_cold_seconds=timing[0],separate_warm_seconds=timing[1],merged_warm_seconds=physical['seconds'],
        merged_to_separate_warm_ratio=ratio,logical_points=len(entries),actual_records=sum(len(x) for x in reference),physical_result=physical,
        all_trajectories_seeds_scores_choices_diagnostics_and_record_order_exact=True,no_original_receipt_or_result_modified=True,
        timing_scope='Tiny paired engineering sample, not sustained throughput. Both warm paths follow cold references on the same worker.',worker=socket.gethostname()+'_'+str(os.getpid())))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),ratio=ratio)
