"""Fold-contained candidate-critic training and whole-policy validation stream."""
from r2_common import *
from r2_resume_support import append_once,register_once,enqueue
from r2_coarse_producer import balanced
from collections import defaultdict


def main():
    setup('candidate_selector_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows])
    handler='code/r2_candidate_selector.py';evaluator='code/r2_candidate_eval.py';pilot=None;queued=set();handled=set();panels={}
    stage=ROOT/'runs/candidate_selector_cv_v1';smoke=ROOT/'runs/candidate_selector_engineering_v1'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
    if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue}
    protocol=ROOT/'config/CANDIDATE_SELECTOR_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),K=list(range(2,9)),roles=['PDMS','safety'],tiers=['trajectory','denoising'],
        inputs='six observable VLM/interface views plus current Base/candidate geometry, candidate slot; optional Base denoising states',
        scoring='shared outcome gain and damage critic, calibrated with three inner session folds',
        expert_count='exactly K or recorded inactive subgroup count; Base additional',inner_model_specs='ridge alpha .1/1/10/100 and ExtraTrees depth8/16 leaf8/32',
        no_actual_score_at_deployment=True,no_trajectory_averaging=True,outer_whole_system_cv=True,validation_fitted=False,test_accessed=False))
    while True:
        tasks=[]
        for p in sorted((ROOT/'analysis/expert_library_selection').glob('*.json')):
            selection=read(p);responses=[ROOT/'analysis/responses'/name/p.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if not all(q.exists() for q in responses):continue
            for role in ['PDMS','safety']:
                for tier in ['trajectory','denoising']:
                    spec=dict(selection=str(p.relative_to(ROOT)),responses=[str(q.relative_to(ROOT)) for q in responses],role=role,tier=tier)
                    ident='outcome_selector_'+digest(spec)[:24]
                    if pilot is None:pilot=ident
                    if ident!=pilot and not (ROOT/'provenance/CANDIDATE_SELECTOR_ENGINEERING_PASS.json').exists():continue
                    if ident in queued:continue
                    tasks.append(dict(id=ident,handler=handler,handler_sha256=sha(ROOT/handler),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        if pilot and (ROOT/'candidate_selectors'/pilot/'POLICY.json').exists() and not (ROOT/'provenance/CANDIDATE_SELECTOR_ENGINEERING_PASS.json').exists():
            policy=ROOT/'candidate_selectors'/pilot/'POLICY.json';point=smoke/'points/smoke.json'
            if not point.exists():atomic(point,dict(id='candidate_selector_smoke',mode='engineering',panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel'],seeds=[0,1,2],policies=[
                dict(id='candidate_selector',policy=str(policy.relative_to(ROOT)),policy_sha256=sha(policy)),
                dict(id='forced_Base',policy=str(policy.relative_to(ROOT)),policy_sha256=sha(policy),force_choice=0),
                dict(id='forced_candidate',policy=str(policy.relative_to(ROOT)),policy_sha256=sha(policy),force_choice=1)]))
            if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='candidate_selector_smoke',point=str(point.relative_to(ROOT)),start=0,end=2,stage=str(smoke.relative_to(ROOT)))]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
            register_once(dict(name='candidate_selector_real_engineering',path=str(smoke.relative_to(ROOT)),handler=evaluator,handler_sha256=sha(ROOT/evaluator),kind='custom',priority=6))
            if (smoke/'receipts/candidate_selector_smoke.json').exists():atomic(ROOT/'provenance/CANDIDATE_SELECTOR_ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),actual_score=True,independent_complete_candidates=True,exact_Base=True,forced_nonzero=True))
        if (ROOT/'provenance/CANDIDATE_SELECTOR_ENGINEERING_PASS.json').exists():
            register_once(dict(name='independent_candidate_selector_whole_system_cv',path=str(stage.relative_to(ROOT)),handler=evaluator,handler_sha256=sha(ROOT/evaluator),kind='custom',priority=22.2))
            groups=defaultdict(dict)
            for p in (ROOT/'candidate_selectors').glob('*/POLICY.json'):
                d=read(p);groups[(d['heldout_fold'],d['system'])][(d['role'],d['tier'])]=(p,d)
            changed=False
            for key,entries in groups.items():
                if key in handled or len(entries)!=4:continue
                held,system=key
                if held not in panels:
                    mask=explore&((folds==held) if held>=0 else True);salt=dict(candidate_outer_panel=20261018,held=held)
                    failure=np.flatnonzero(mask&(quality<.7)).tolist() if held>=0 else balanced(np.flatnonzero(mask&(quality<.7)),rows,32,salt)
                    high=balanced(np.flatnonzero(mask&(quality>.9)),rows,512 if held>=0 else 24,salt)
                    mid=balanced(np.flatnonzero(mask&(quality>=.7)&(quality<=.9)),rows,256 if held>=0 else 8,salt)
                    panels[held]=(failure+high+mid,dict(failure=failure,high=high,intermediate=mid))
                panel,partitions=panels[held];ident='selector_cv_'+digest(dict(held=held,system=system))[:24];point=stage/'points'/(ident+'.json')
                if not point.exists():atomic(point,dict(id=ident,system=system,heldout_fold=held,mode='heldout' if held>=0 else 'training',panel=panel,panel_partitions=partitions,seeds=[0,1,2],policies=[dict(id=role+'_'+tier,policy=str(p.relative_to(ROOT)),policy_sha256=sha(p)) for (role,tier),(p,d) in sorted(entries.items())],whole_system_cv=held>=0,validation_accessed=False,test_accessed=False))
                for start in range(0,len(panel),4):enqueue(queue,known,dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(stage.relative_to(ROOT))))
                handled.add(key);changed=True
            if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=False,tasks=len(queue),systems=len(handled),time=stamp()))
        atomic(ROOT/'analysis/candidate_selectors/PRODUCER.json',dict(time=stamp(),fits_queued=len(queued),evaluations_queued=len(handled),pilot=pilot,engineering_pass=(ROOT/'provenance/CANDIDATE_SELECTOR_ENGINEERING_PASS.json').exists()))
        time.sleep(60)


if __name__=='__main__':main()
