"""Actual finite-action objective controls; replay warm then continue without GT."""
from r2_common import *
from r2_resume_support import register_once,enqueue
import re


def main():
    setup('finite_router_producer')
    source=next(t for t in read(ROOT/'runs/behavior_router_training_v1/tasks.json') if t['kind']=='hard_continuous' and t['tier']=='trajectory' and t['role']=='PDMS' and read(ROOT/t['selection'])['system']=='representation_K2_seed0' and read(ROOT/t['selection'])['heldout_fold']==-1)
    bank=next(str(p.relative_to(ROOT)) for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json') if read(p)['system']=='representation_K2_seed0' and read(p)['heldout_fold']==-1)
    smoke=ROOT/'runs/finite_outcome_router_engineering_v1'
    if not (smoke/'tasks.json').exists():atomic(smoke/'tasks.json',[dict(id='finite_outcome_router_engineering_v1',stage=str(smoke.relative_to(ROOT)),source=source,bank=bank)]);atomic(smoke/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    handler='code/r2_finite_router_smoke.py';register_once(dict(name='actual_outcome_neural_routing_engineering',path=str(smoke.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not (ROOT/'provenance/FINITE_OUTCOME_ROUTER_ENGINEERING_PASS.json').exists():time.sleep(15)
    protocol=ROOT/'config/FINITE_OUTCOME_ROUTER_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_DISCOVERY',time=stamp(),initial_K=[2,3,4],initial_replicate=0,all_three_families=True,folds=[-1,0,1,2,3,4],
        input_tiers=['observation','trajectory'],roles=['PDMS','safety'],methods=['ce_continuation','regret_uniform','regret_natural'],steps=2048,checkpoints=[128,512,2048],
        common_prefix='Exact original scored-response CE warm128; consume the same512-step training schedule RNG before warm.',
        interpretation='Keep warm checkpoint; continue true-outcome CE or choose-one expected regret, versus the existing GT/trajectory proxy training.',
        natural_objective='Regret weighted by actual training-fold S0 quality proportions; uniform variant separates weighting from objective.',
        safety_labels='Base NC/DAC value and zero-score nonworsening labels, used only for fitting.',
        inference='Hard categorical fixed expert or exact Base, amount1. Cached true outcomes looked up after choices; no new candidate generation.',
        no_hidden_mixture_linearity_claim=True,need_finalist_replicate_confirmation=True,validation_accessed=False,test_accessed=False))
    train=ROOT/'runs/finite_outcome_router_training_v1';ev=ROOT/'runs/finite_outcome_router_cv_v1'
    for stage,handler,priority in [(train,'code/r2_finite_router.py',24.3),(ev,'code/r2_finite_router_predict.py',22.3)]:
        if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[]);atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name=stage.name,path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=priority,enabled=False))
    queue=read(train/'tasks.json');known={t['id'] for t in queue};eq=read(ev/'tasks.json');ek={t['id'] for t in eq};handled=set()
    sources=[dict(folder='expert_library_selection',s0='expert_library_S0_v1',noise='expert_library_noise_v1'),dict(folder='causal_library_selection',s0='causal_library_S0_v1',noise='causal_library_noise_v1'),dict(folder='variant_library_selection',s0='variant_library_S0_v1',noise='variant_library_noise_v1')]
    while True:
        admitted=set(read(ROOT/'config/FINITE_ROUTER_REPLICATION_ADMISSION_V1.json')['systems'])
        banks={}
        for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
            d=read(p)
            if d['mode']=='heldout':banks[(d['heldout_fold'],d['system'])]=(p,d)
        changed=False;ec=False;eligible=[]
        for source in sources+read(ROOT/'config/ADDITIONAL_BANK_SOURCES.json')['sources']:
            for p in (ROOT/'analysis'/source['folder']).glob('*.json'):
                d=read(p);match=re.search(r'_K(\d+)_seed([0-2])$',d['system']);assert match
                if not ((int(match[1]) in [2,3,4] and int(match[2])==0) or d['system'] in admitted):continue
                responses=[ROOT/'analysis/responses'/name/p.name for name in [source['s0'],source['noise']]]
                if all(q.exists() for q in responses):eligible.append((p,d,responses))
        eligible.sort(key=lambda x:(0 if x[1]['heldout_fold']>=0 else 1,x[1]['K'],x[1]['heldout_fold'],x[1]['system']))
        for path,selection,responses in eligible:
            models=[]
            for method in ['ce_continuation','regret_uniform','regret_natural']:
                for role in ['PDMS','safety']:
                    for tier in ['observation','trajectory']:
                        spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses],method=method,role=role,tier=tier,fit_seed=2026101801+int(re.search(r'_seed([0-2])$',selection['system'])[1]),
                            steps=2048,warmup_steps=128,original_proxy_steps=512,checkpoints=[128,512,2048],science_phase='formal')
                        ident='finite_router_'+digest(spec)[:24]
                        if ident not in known:enqueue(queue,known,dict(id=ident,**spec));changed=True
                        p=ROOT/'finite_outcome_routers'/ident/'TRAINING.json'
                        if p.exists():
                            model=read(p);assert model['task']['science_phase']=='formal' and model['task']['steps']==2048;models.append(model)
            key=(selection['heldout_fold'],selection['system']);cache=banks.get(key)
            if key in handled or cache is None or len(models)!=12:continue
            cache_path,cache_meta=cache
            with __import__('numpy').load(ROOT/cache_meta['matrix']) as z:panel=z['global_indices'].tolist();available=set(z['arm_ids'].tolist())
            assert all(p['id'] in available for m in models for p in m['parts']);policies=[]
            for m in models:
                for ck in m['checkpoints']:
                    if ck['step']==128 and m['method']!='ce_continuation':continue
                    policies.append(dict(id=m['method']+'_'+str(ck['step'])+'_'+m['role']+'_'+m['tier'],model=m,checkpoint=ck))
            ident='finite_cv_'+digest(dict(held=key[0],system=key[1]))[:24];point=ev/'points'/(ident+'.json')
            if not point.exists():atomic(point,dict(id=ident,mode='heldout',kind='finite_outcome',heldout_fold=key[0],system=key[1],bank=str(cache_path.relative_to(ROOT)),panel=panel,seeds=[0,1,2],policies=policies,whole_system_outer_cv=True))
            for start in range(0,len(panel),4):enqueue(eq,ek,dict(id=ident+'_%04d'%start,stage=str(ev.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel))))
            handled.add(key);ec=True
        if changed:atomic(train/'tasks.json',queue);atomic(train/'producer.json',dict(complete=False,tasks=len(queue),time=stamp()))
        if ec:atomic(ev/'tasks.json',eq);atomic(ev/'producer.json',dict(complete=False,tasks=len(eq),systems=len(handled),time=stamp()))
        atomic(ROOT/'analysis/finite_outcome_router_pipeline/PRODUCER.json',dict(time=stamp(),training_tasks=len(queue),held_systems_queued=len(handled)))
        time.sleep(60)


def await_metadata_handoff():
    config=read(ROOT/'config/FINITE_ROUTER_REPLICATION_ADMISSION_V1.json');targets=set(config['systems']);ready=ROOT/'runs/finite_replication_handoff/READY.json';release=ROOT/'runs/finite_replication_handoff/RELEASE.json'
    while not ready.exists():
        found=[]
        for p in (ROOT/'analysis/spatial_library_selection').glob('*.json'):
            d=read(p)
            if d['system'] in targets and all((ROOT/'analysis/responses'/n/p.name).exists() for n in ['spatial_library_S0_v1','spatial_library_noise_v1']):found.append(dict(selection=str(p.relative_to(ROOT)),system=d['system'],held=d['heldout_fold']))
        if found:atomic(ready,dict(status='READY_FOR_OWN_METADATA_PRODUCER_HANDOFF',time=stamp(),banks=found,no_automatic_stop_or_shared_queue_write=True))
        else:time.sleep(60)
    while not release.exists():time.sleep(60)
    d=read(release);assert d['status']=='OLD_METADATA_STOPPED_RELEASE_NEW_PRODUCER' and (ROOT/d['retirement_evidence']).exists()


if __name__=='__main__':await_metadata_handoff();main()
