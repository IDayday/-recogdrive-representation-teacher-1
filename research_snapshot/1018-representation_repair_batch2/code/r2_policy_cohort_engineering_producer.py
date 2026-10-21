"""One exact pilot, then the frozen16 engineering cohorts; no adoption decision."""
from r2_common import *
from r2_resume_support import register_once


def main():
    import statistics
    config=read(ROOT/'config/POLICY_COHORT_ENGINEERING_PROTOCOL_V1.json');stage=ROOT/config['stage'];tasks=read(ROOT/config['tasks'])
    handler='code/r2_policy_cohort_engineering.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',tasks[:1]);atomic(stage/'producer.json',dict(complete=False,time=stamp(),tasks=1))
    register_once(dict(name='shared_scene_policy_cohort_exact_AB_engineering',path=config['stage'],handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not (stage/'receipts'/(tasks[0]['id']+'.json')).exists():time.sleep(15)
    first=read(stage/'receipts'/(tasks[0]['id']+'.json'));proof=read(ROOT/first['result']['path']);assert proof['all_trajectories_seeds_scores_choices_diagnostics_and_record_order_exact']
    assert read(stage/'tasks.json') in [tasks[:1],tasks]
    atomic(stage/'tasks.json',tasks);atomic(stage/'producer.json',dict(complete=True,time=stamp(),tasks=len(tasks)))
    while not all((stage/'receipts'/(t['id']+'.json')).exists() for t in tasks):time.sleep(30)
    proofs=[]
    for t in tasks:
        r=read(stage/'receipts'/(t['id']+'.json'));assert sha(ROOT/r['result']['path'])==r['result']['sha256'];d=read(ROOT/r['result']['path']);assert d['status']=='PASS_EXACT_RECORDS';proofs.append(d)
    groups=[]
    for handler in sorted({p['handler'] for p in proofs}):
        for mode in config['modes']:
            own=[p for p in proofs if p['handler']==handler and p['task']['evaluation_mode']==mode];assert len(own)==config['cohorts_per_context']
            ratios=[p['merged_to_separate_warm_ratio'] for p in own];groups.append(dict(handler=handler,mode=mode,cohorts=len(own),median_ratio=statistics.median(ratios),ratios=ratios,median_ratio_below_predeclared_point9=statistics.median(ratios)<.9))
    path=ROOT/'provenance/POLICY_COHORT_ENGINEERING_SUMMARY.json';atomic(path,dict(status='ALL16_EXACT_ENGINEERING_COHORTS_COMPLETE',time=stamp(),protocol='config/POLICY_COHORT_ENGINEERING_PROTOCOL_V1.json',groups=groups,actual_cohorts=len(proofs),actual_logical_records=sum(p['actual_records'] for p in proofs),distinct_workers=len({p['worker'] for p in proofs}),proofs=proofs,
        all_original_evaluators_unchanged=True,all_trajectory_seed_score_choice_diagnostic_record_order_exact=True,no_production_adoption_or_original_queue_change=True,agent_must_review_timing_and_remaining_work=True))
    print(json.dumps(dict(status='COMPLETE',path=str(path.relative_to(ROOT)),groups=groups)),flush=True)


if __name__=='__main__':main()
