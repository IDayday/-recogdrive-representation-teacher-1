"""Cheap full-token calibration/CV by reusing immutable complete candidate banks.

Only token-conditioned predictions are new GPU work. Every candidate and true
outcome comes from an independently generated, actually scored frozen trajectory.
Selected rules are locked on training calibration sessions before held evaluation.
"""
from r2_common import *
from r2_resume_support import append_once,register_once,enqueue
import re


def main():
    setup('token_policy_producer')
    import numpy as np
    from r2_token_critic import inner_session
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);calibration=np.asarray([inner_session(r['session']) for r in rows])
    folds=np.asarray([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    stages=[ROOT/'runs/additional_token_critic_calibration_v1',ROOT/'runs/additional_token_critic_held_predictions_v1'];queues={};known={}
    for base,priority in zip(stages,[23.7,22.3]):
        if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
        if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
        queues[base]=read(base/'tasks.json');known[base]={t['id'] for t in queues[base]}
        register_once(dict(name=base.name,path=str(base.relative_to(ROOT)),handler='code/r2_token_predict.py',handler_sha256=sha(ROOT/'code/r2_token_predict.py'),kind='custom',priority=priority))
    protocol=ROOT/'config/TOKEN_CRITIC_POLICY_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),calibration='Only hashed one-of-seven outer-training sessions excluded from critic gradient training; score unchanged existing full candidate trajectories.',
        critic_initialization='Match expert-system fit replicate, never choose the best seed.',checkpoints=[4000,8000],risk_penalty=[0.,.1,.5,1.,2.,5.],threshold=[0.,.001,.005,.01,.02,.05,.1,2.],
        roles=['PDMS','safety'],whole_system_held='All prior independent candidate-cache rows: held failures plus512high/256intermediate, S0/S1/S2.',
        efficiency='Reuse actual unchanged candidates and scores; only new token-critic predictions require GPU. Final test still runs fresh frozen generation and independent scoring.',
        risk_proxy='Predicted NC and DAC deterioration; actual zero-score nonincrease also constrains safety calibration.',
        validation_accessed=False,test_accessed=False))
    prepared=set();calibrated=set();held_prepared=set();assessed=set();response_indices={}
    while True:
        models={}
        for path in (ROOT/'token_critics').glob('*/TRAINING.json'):
            d=read(path)
            if 'wave' not in d['task']:continue
            key=(d['heldout_fold'],d['task']['wave'],d['fit_seed']);assert key not in models;models[key]=d
        candidate_banks={}
        for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
            d=read(p);candidate_banks[(d['heldout_fold'],d['system'])]=(p,d)
        changed=set();cpu_tasks=[];bank_specs=[(s['folder'],s['s0'],s['noise']) for s in read(ROOT/'config/ADDITIONAL_BANK_SOURCES.json')['sources']]
        for folder,s0,noise in bank_specs:
            for selection_path in (ROOT/'analysis'/folder).glob('*.json'):
                bank=read(selection_path);held=bank['heldout_fold'];system=bank['system'];match=re.search(r'seed([0-2])(?:\D|$)',system);assert match
                fit_seed=2026101801+int(match.group(1));response_paths=[ROOT/'analysis/responses'/name/selection_path.name for name in [s0,noise]]
                if not all(p.exists() for p in response_paths):continue
                by_id={p['id']:p for p in bank['arms']}
                for wave in [1,2]:
                    model=models.get((held,wave,fit_seed))
                    if model is None:continue
                    for role in ['PDMS','safety']:
                        config=dict(held=held,system=system,wave=wave,role=role,fit_seed=fit_seed,model=model['task']['id'])
                        ident='token_cal_'+digest(config)[:24];point_path=stages[0]/'points'/(ident+'.json')
                        if ident not in prepared:
                            items=[]
                            for p in response_paths:
                                path=str(p.relative_to(ROOT))
                                if path not in response_indices:
                                    response=read(p)
                                    with np.load(ROOT/response['matrix']) as z:response_indices[path]=np.array(z['global_indices'])
                                indices=response_indices[path];assert held<0 or np.all(folds[indices]!=held)
                                items.extend([[path,int(j)] for j in np.flatnonzero(calibration[indices])])
                            parts=[by_id[v] for _,v in sorted(bank['policies'][role].items(),key=lambda p:int(p[0]))]
                            critics=[dict(id='token_ck_'+digest(ck)[:24],checkpoint=ck,heldout_fold=held) for ck in model['checkpoints']]
                            if not point_path.exists():atomic(point_path,dict(id=ident,mode='calibration',heldout_fold=held,system=system,K=bank['K'],wave=wave,fit_seed=fit_seed,role=role,
                                selection=str(selection_path.relative_to(ROOT)),parts=parts,critics=critics,items=items,responses=[str(p.relative_to(ROOT)) for p in response_paths],training_only=True))
                            for start in range(0,len(items),8):enqueue(queues[stages[0]],known[stages[0]],dict(id=ident+'_%04d'%start,point=str(point_path.relative_to(ROOT)),start=start,end=min(start+8,len(items)),stage=str(stages[0].relative_to(ROOT))))
                            prepared.add(ident);changed.add(stages[0])
                        point=read(point_path);chunks=[ident+'_%04d'%start for start in range(0,len(point['items']),8)]
                        if ident not in calibrated and all((stages[0]/'receipts'/(c+'.json')).exists() for c in chunks):
                            cpu_tasks.append(dict(id='outcome_token_calibration_'+ident,handler='code/r2_token_policy_select.py',handler_sha256=sha(ROOT/'code/r2_token_policy_select.py'),point=str(point_path.relative_to(ROOT)),stage=str(stages[0].relative_to(ROOT))));calibrated.add(ident)
                        policy_path=ROOT/'token_policies'/ident/'POLICY.json'
                        if held<0 or not policy_path.exists():continue
                        cache=candidate_banks.get((held,system))
                        if cache is None:continue
                        held_id='token_held_'+ident;held_point=stages[1]/'points'/(held_id+'.json')
                        if held_id not in held_prepared:
                            policy=read(policy_path);cache_path,cache_meta=cache;assert cache_meta['mode']=='heldout'
                            with np.load(ROOT/cache_meta['matrix']) as z:indices=np.array(z['global_indices']);arm_ids=list(z['arm_ids'])
                            assert np.all(folds[indices]==held) and all(p['id'] in arm_ids for p in policy['parts'])
                            items=[[str(cache_path.relative_to(ROOT)),j] for j in range(len(indices))]
                            if not held_point.exists():atomic(held_point,dict(id=held_id,mode='heldout',heldout_fold=held,system=system,K=bank['K'],wave=wave,fit_seed=fit_seed,role=role,
                                parts=policy['parts'],critics=[policy['critic']],items=items,responses=[str(cache_path.relative_to(ROOT))],policy=str(policy_path.relative_to(ROOT)),policy_sha256=sha(policy_path),whole_system_cv=True))
                            for start in range(0,len(items),8):enqueue(queues[stages[1]],known[stages[1]],dict(id=held_id+'_%04d'%start,point=str(held_point.relative_to(ROOT)),start=start,end=min(start+8,len(items)),stage=str(stages[1].relative_to(ROOT))))
                            held_prepared.add(held_id);changed.add(stages[1])
                        point=read(held_point);chunks=[held_id+'_%04d'%start for start in range(0,len(point['items']),8)]
                        if held_id not in assessed and all((stages[1]/'receipts'/(c+'.json')).exists() for c in chunks):
                            cpu_tasks.append(dict(id='outcome_token_held_assess_'+ident,handler='code/r2_token_policy_assess.py',handler_sha256=sha(ROOT/'code/r2_token_policy_assess.py'),point=str(held_point.relative_to(ROOT)),stage=str(stages[1].relative_to(ROOT))));assessed.add(held_id)
        if cpu_tasks:append_once('cpu',cpu_tasks)
        for base in changed:atomic(base/'tasks.json',queues[base]);atomic(base/'producer.json',dict(complete=False,tasks=len(queues[base]),time=stamp()))
        atomic(ROOT/'analysis/additional_token_policy_pipeline/PRODUCER.json',dict(time=stamp(),critics_trained=len(models),calibration_points=len(prepared),calibration_cpu_queued=len(calibrated),held_points=len(held_prepared),held_assess_queued=len(assessed)))
        time.sleep(60)


if __name__=='__main__':main()
