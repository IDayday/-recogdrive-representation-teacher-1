"""Hierarchical genuine joint routing for heterogeneous and regrouped experts."""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced
import re


def main():
    setup('additional_joint_producer')
    import numpy as np
    while not (ROOT/'provenance/RAW_MULTISITE_ROUTER_ENGINEERING_PASS.json').exists():time.sleep(15)
    protocol=ROOT/'config/ADDITIONAL_JOINT_ROUTER_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_DISCOVERY_WAVE',time=stamp(),
        initial_sources=['causal_library_selection','variant_library_selection','unified_bcs_library_selection'],
        initial_K=[2,3,4],initial_replicate=0,families=['representation','response','correction'],folds=[-1,0,1,2,3,4],
        modes=['hard_continuous','soft_joint'],roles=['PDMS','safety'],tiers=['observation','trajectory','denoising'],
        steps=dict(hard_continuous=512,soft_joint=768),warmup_steps=128,
        followup='Additional K5..8, pure spatial, and fitting replicas1/2 admitted for retained recipes using explicit admission file before independent confirmation.',
        all_K_context='Original learned bank retains full dense K2..8 sweep. Fixed hard and independent-candidate routers cover all new banks/all K.',
        no_linear_outcome_assumption=True,validation_accessed=False,test_accessed=False))
    admission=ROOT/'config/ADDITIONAL_JOINT_ADMISSION.json'
    if not admission.exists():atomic(admission,dict(recipes=[],admit_all=False))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows])
    train=ROOT/'runs/additional_joint_training_v1';ev=ROOT/'runs/additional_joint_quick_v1'
    for stage,handler,priority in [(train,'code/r2_additional_joint_train.py',24.65),(ev,'code/r2_additional_joint_eval.py',23.82)]:
        if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
        if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        register_once(dict(name=stage.name,path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=priority,enabled=False))
    queue=read(train/'tasks.json');known={t['id'] for t in queue};eq=read(ev/'tasks.json');ek={t['id'] for t in eq};handled=set();panels={}
    sources=[dict(folder='causal_library_selection',s0='causal_library_S0_v1',noise='causal_library_noise_v1'),dict(folder='variant_library_selection',s0='variant_library_S0_v1',noise='variant_library_noise_v1')]
    while True:
        changes=False;ec=False;allow=read(admission)
        all_sources=sources+read(ROOT/'config/ADDITIONAL_BANK_SOURCES.json')['sources']
        for src in all_sources:
            for path in (ROOT/'analysis'/src['folder']).glob('*.json'):
                selection=read(path);held=selection['heldout_fold'];system=selection['system'];match=re.match(r'(.+)_K(\d+)_seed([0-2])$',system);assert match
                recipe=dict(source=src['folder'],family=match[1],K=int(match[2]),replicate=int(match[3]))
                eligible=src['folder'] in read(protocol)['initial_sources'] and recipe['K'] in [2,3,4] and recipe['replicate']==0
                eligible=eligible or allow.get('admit_all',False) or any(all(recipe.get(k)==v for k,v in row.items()) for row in allow['recipes'])
                if not eligible:continue
                responses=[ROOT/'analysis/responses'/name/path.name for name in [src['s0'],src['noise']]]
                if not all(p.exists() for p in responses):continue
                if held not in panels:
                    mask=explore&((folds!=held) if held>=0 else True);salt=dict(joint_router_quick=20261018,held=held)
                    parts={n:balanced(np.flatnonzero(mask&condition),rows,count,salt) for n,condition,count in [('failure',quality<.7,32),('high',quality>.9,24),('intermediate',(quality>=.7)&(quality<=.9),8)]};panels[held]=(sum(parts.values(),[]),parts)
                for kind in ['hard_continuous','soft_joint']:
                    for tier in ['observation','trajectory','denoising']:
                        for role in ['PDMS','safety']:
                            spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses],kind=kind,tier=tier,role=role)
                            ident='additional_joint_'+digest(spec)[:24];steps=512 if kind=='hard_continuous' else 768
                            task=dict(id=ident,**spec,steps=steps,checkpoints=[steps//2,steps],warmup_steps=128,retention_weight=4. if role=='safety' else 2.,fit_seed=2026101801+recipe['replicate'])
                            if ident not in known:enqueue(queue,known,task);changes=True
                            model_path=ROOT/'behavior_routers'/ident/'TRAINING.json'
                            if ident in handled or not model_path.exists():continue
                            model=read(model_path);descriptions=[]
                            for ck in model['checkpoints']:
                                for multiplier in [.5,1.]:
                                    for threshold in [.5,.9,1.01]:
                                        config=dict(checkpoint=ck,multiplier=multiplier,identity_threshold=threshold)
                                        descriptions.append(dict(id='additional_joint_config_'+digest(config)[:24],model=model,**config))
                            panel,partitions=panels[held];point=ev/'points'/(ident+'.json')
                            if not point.exists():atomic(point,dict(id=ident,heldout_fold=held,training_only=True,mode='training',policies=descriptions,panel=panel,panel_partitions=partitions,seeds=[0,1,2],training_path=str(model_path.relative_to(ROOT))))
                            for start in range(0,len(panel),4):enqueue(eq,ek,dict(id=ident+'_%04d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(ev.relative_to(ROOT))))
                            handled.add(ident);ec=True
        if changes:atomic(train/'tasks.json',queue);atomic(train/'producer.json',dict(complete=False,tasks=len(queue),time=stamp()))
        if ec:atomic(ev/'tasks.json',eq);atomic(ev/'producer.json',dict(complete=False,tasks=len(eq),models=len(handled),time=stamp()))
        atomic(ROOT/'analysis/additional_joint/PRODUCER.json',dict(time=stamp(),models_queued=len(queue),models_reevaluation_queued=len(handled),initial_sources=read(protocol)['initial_sources']))
        time.sleep(60)


if __name__=='__main__':main()
