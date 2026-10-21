"""Strict complete-natural evaluation, paired safety and privileged diagnostics.

Prepared before finalist choice. Noise repetitions stay paired within scene;
session-cluster resampling includes all scenes and all draws of that session.
"""
from r2_common import *


def metrics(base,after,sessions,bootstrap=2000):
    import numpy as np
    n,k,_=base.shape;delta=(after[:,:,0]-base[:,:,0])*100;unique=sorted(set(sessions));lookup={v:j for j,v in enumerate(unique)};ss=np.zeros((len(unique),2))
    for j,name in enumerate(sessions):ss[lookup[name],0]+=delta[j].mean();ss[lookup[name],1]+=1
    rng=np.random.default_rng(2026101811);values=[]
    for start in range(0,bootstrap,100):
        pick=rng.integers(len(unique),size=(min(100,bootstrap-start),len(unique)));s=ss[pick].sum(1);values.extend((s[:,0]/s[:,1]).tolist())
    event_base=np.stack([base[:,:,1]<1,base[:,:,2]<1,base[:,:,0]==0,base[:,:,3]<1,base[:,:,0]<.7],-1)
    event_after=np.stack([after[:,:,1]<1,after[:,:,2]<1,after[:,:,0]==0,after[:,:,3]<1,after[:,:,0]<.7],-1)
    new=np.sum(event_after&~event_base,axis=0);resolved=np.sum(event_base&~event_after,axis=0);net=new-resolved
    per_seed=delta.mean(0);classes=np.where(base[:,0,0]<.7,0,np.where(base[:,0,0]>.9,1,2));class_metrics={}
    for c in range(3):
        mask=classes==c;class_metrics[str(c)]=dict(cases=int(mask.sum()),mean_gain=float(delta[mask].mean()) if np.any(mask) else None)
    return dict(cases=n,noise_draws=k,Base_PDMS_by_noise=(base[:,:,0].mean(0)*100).tolist(),PDMS_by_noise=(after[:,:,0].mean(0)*100).tolist(),
        PDMS_gain_by_noise=per_seed.tolist(),mean_PDMS_gain=float(delta.mean()),session_bootstrap_95=np.quantile(values,[.025,.975]).tolist(),
        newly_bad_by_noise=new.tolist(),resolved_bad_by_noise=resolved.tolist(),net_bad_by_noise=net.tolist(),safety_all_noise=bool(np.all(net[:,:3]<=0)),
        repaired70_by_noise=np.sum((base[:,:,0]<.7)&(after[:,:,0]>=.7),axis=0).tolist(),repaired90_by_noise=np.sum((base[:,:,0]<.7)&(after[:,:,0]>.9),axis=0).tolist(),
        lost_high_by_noise=np.sum((base[:,:,0]>.9)&(after[:,:,0]<=.9),axis=0).tolist(),damaged_by_noise=np.sum(delta< -1e-6,axis=0).tolist(),
        S0_quality_classes=class_metrics,event_columns=['collision','offroad','zero','TTC','failure'])


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    from r2_point_response import FIELDS
    stage=ROOT/task['stage'];tasks=read(stage/'tasks.json');assert tasks
    evaluate=[t.get('evaluation',t) for t in tasks];first=evaluate[0];mode=first['mode'];pack=read(ROOT/first['pack']);lock=read(ROOT/first['lock']);assert sha(ROOT/first['pack'])==first['pack_sha256']==lock['pack_sha256']
    assert sha(ROOT/first['rows'])==first['rows_sha256']==lock['rows_sha256'];rows=read(ROOT/first['rows']);seeds=first['seeds'];panel=first['panel'];names=None;score=None;seen=set();sources=[];row_position={int(i):j for j,i in enumerate(panel)};token_position={rows[i]['token']:j for i,j in row_position.items()};seed_position={v:j for j,v in enumerate(seeds)}
    for t,e in zip(tasks,evaluate):
        assert e['pack_sha256']==first['pack_sha256'] and e['rows_sha256']==first['rows_sha256'] and e['seeds']==seeds and e['panel']==panel and e['mode']==mode
        receipt=stage/'receipts'/(t['id']+'.json');assert receipt.exists(),('Missing receipt',receipt)
        r=read(receipt);result=r['result']
        if 'sha256' not in result:
            assert mode=='engineering';proof=read(ROOT/result['path']);assert proof['status']=='PASS';result=proof['result']
        path=ROOT/result['path'];assert sha(path)==result['sha256'];chunk=read(path)
        for record in chunk['records']:
            if names is None:
                names=list(dict.fromkeys(v['arm'] for v in chunk['records']));arm_position={v:j for j,v in enumerate(names)};score=np.full((len(panel),len(names),len(seeds),len(FIELDS)),np.nan)
            key=(token_position[record['token']],arm_position[record['arm']],seed_position[record['seed_index']]);assert key not in seen;seen.add(key)
            noise=record.get('noise_draw_index',record['seed_index']);assert record['seed']==seed(record['token'],noise)
            score[key]=[record['score'][f] for f in FIELDS]
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=result['sha256']))
    assert np.isfinite(score).all() and len(seen)==len(panel)*len(names)*len(seeds)
    if mode=='validation':assert len(panel)==17475 and len(panel)==len(rows) and all(r['subset']=='validation' for r in rows)
    if mode=='test':assert lock['final_test_selection_frozen'] and seeds==[0,1,2,3,4] and len(panel)==len(rows) and all(r['subset']=='test' for r in rows)
    sessions=[rows[i]['session'] for i in panel];base=score[:,arm_position['baseline']];summaries={};diagnostics={};B=task.get('bootstrap_samples',2000)
    def report(after):return metrics(base,after,sessions,B)
    for config in pack['policies']:
        ident=config['id'];after=score[:,arm_position[ident]];summaries[ident]=report(after)
        if config['kind']=='Base':continue
        policy=read(ROOT/config['policy']);parts=policy['configuration']['model']['parts'] if config['kind'] in ['joint','finite'] else policy['parts'];d={}
        d['perfect_failure_trigger']=report(np.where((base[:,:,0]<.7)[:,:,None],after,base))
        d['beneficial_replacement_only']=report(np.where((after[:,:,0]>base[:,:,0])[:,:,None],after,base))
        if pack.get('include_raw_experts',True):
            candidates=score[:,[arm_position['baseline']]+[arm_position['candidate_'+p['id']] for p in parts]];ii=np.arange(len(panel))[:,None];nn=np.arange(len(seeds))[None,:]
            best=candidates[:,:,:,0].argmax(1);oracle=candidates[ii,best,nn];d['actual_candidate_oracle']=report(oracle)
            d['oracle_only_Base_failures']=report(np.where((base[:,:,0]<.7)[:,:,None],oracle,base))
            eligible=(candidates[:,:,:,1]>=base[:,None,:,1])&(candidates[:,:,:,2]>=base[:,None,:,2])&(~(candidates[:,:,:,0]==0)|(base[:,None,:,0]==0))
            safe_choice=np.where(eligible,candidates[:,:,:,0],-np.inf).argmax(1);d['per_case_safety_constrained_oracle']=report(candidates[ii,safe_choice,nn])
            fixed=candidates[:,:,0,0].argmax(1);d['S0_fixed_candidate_cross_noise']=report(candidates[np.arange(len(panel)),fixed])
            fixed_all=candidates[:,:,:,0].mean(2).argmax(1);d['all_noise_privileged_scene_fixed_oracle']=report(candidates[np.arange(len(panel)),fixed_all])
        K=len(parts);maximum=pack.get('base_resampling_extra_candidates',0)
        if maximum>=K:
            pool=score[:,[arm_position['baseline']]+[arm_position['base_resample_'+str(j)] for j in range(1,K+1)]];choice=pool[:,:,:,0].argmax(1);d['matched_'+str(K+1)+'_Base_draw_oracle']=report(pool[np.arange(len(panel))[:,None],choice,np.arange(len(seeds))[None,:]])
        diagnostics[ident]=d
    folder=ROOT/'analysis/frozen_natural_assessment'/task['id'];folder.mkdir(parents=True,exist_ok=False);matrix=folder/'scores.npz';hashed=save_npz(matrix,scores=score,arms=np.asarray(names),seeds=np.asarray(seeds),panel=np.asarray(panel))
    atomic(folder/'SUMMARY.json',dict(status='COMPLETE_NATURAL_EVALUATION' if mode!='engineering' else 'ENGINEERING_ONLY',time=stamp(),mode=mode,task=task,pack=first['pack'],pack_sha256=first['pack_sha256'],lock=first['lock'],rows=first['rows'],rows_sha256=first['rows_sha256'],cases=len(panel),sessions=len(set(sessions)),noise_indices=seeds,results=summaries,privileged_diagnostics=diagnostics,matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,sources=sources,
        uncertainty='Session-cluster bootstrap of paired scene-average changes; noise repetitions remain inside their scene. Multiplicity across the locked policy family is handled separately in confirmation.',oracle_is_not_deployable=True))
    return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),matrix_sha256=hashed,cases=len(panel))
