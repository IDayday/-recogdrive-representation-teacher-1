"""CPU-only uncertainty/consensus selection of actual complete candidates.

Aggregates predictions, never hidden perturbations or trajectory coordinates.
Calibrate on excluded training sessions, freeze, then read held true outcomes.
"""
from r2_common import *


def choose(prediction,setting,members):
    import numpy as np
    from r2_token_policy_select import choices
    if setting.get('identity'):return np.zeros(len(prediction),dtype=int)
    if setting['method']=='vote':
        votes=np.stack([choices(prediction[:,j],m['risk_penalty'],m['threshold']) for j,m in enumerate(members)],axis=1);counts=np.stack([(votes==a).sum(1) for a in range(prediction.shape[2])],axis=1);winner=counts.argmax(1);winner[counts.max(1)<setting['minimum_votes']]=0;return winner
    gain=np.clip(prediction[:,:,1:,0]-prediction[:,:,:1,0],-1.,1.);risk=np.maximum(prediction[:,:,:1,1:3]-prediction[:,:,1:,1:3],0).sum(3)
    utility=gain.mean(1)-setting['risk_penalty']*risk.mean(1)-setting['beta']*gain.std(1);selected=utility.argmax(1)+1;selected[utility.max(1)<=setting['threshold']]=0;return selected


def run(task):
    import numpy as np
    from r2_token_policy_select import matrices,choices
    from r2_token_critic import inner_session
    from r2_expert_space import save_npz
    protocol=read(ROOT/task['protocol']);assert sha(ROOT/task['protocol'])==task['protocol_sha256'];source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);policies=[read(ROOT/m['policy']) for m in task['members']];held=task['heldout_fold'];assert [p['fit_seed'] for p in policies]==[2026101801,2026101802,2026101803];parts=policies[0]['parts'];assert all(digest(p['parts'])==digest(parts) and p['heldout_fold']==held and p['role']==task['role'] for p in policies)
    cp=[];cal=None;cal_sources=[]
    for spec,p in zip(task['members'],policies):
        assert sha(ROOT/spec['policy'])==spec['policy_sha256'];point=read(ROOT/p['source_point']);d,lineage=matrices(point,spec['calibration_stage']);j=p['selected_calibration']['critic_index'];assert point['critics'][j]['checkpoint']==p['critic']['checkpoint'];cp.append(d['predicted'][:,j]);cal_sources.extend(lineage)
        if cal is None:cal=d
        else:assert all(np.array_equal(cal[k],d[k]) for k in ['global_indices','seeds','scores','trajectory'])
    prediction=np.stack(cp,axis=1);members=[p['critic'] for p in policies];indices=cal['global_indices'];allowed=np.array([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held for r in rows]);assert np.all(allowed[indices]) and all(inner_session(rows[int(i)]['session']) for i in indices)
    cls=np.where(q[indices]<.7,0,np.where(q[indices]>.9,1,2));count=np.bincount(cls,minlength=3);pop=np.array([np.sum(allowed&(q<.7)),np.sum(allowed&(q>.9)),np.sum(allowed&(q>=.7)&(q<=.9))]);w=pop[cls]/count[cls];w/=w.sum();base=cal['scores'][:,0];candidates={m:[] for m in protocol['methods']}
    for method in protocol['methods']:
        if method=='vote':grid=[dict(method=method,minimum_votes=v) for v in [2,3]]+[dict(method=method,identity=True)]
        else:grid=[dict(method=method,beta=b,risk_penalty=r,threshold=t) for b in ([0.] if method=='mean' else [.5,1.,2.]) for r in protocol['risk_penalties'] for t in protocol['thresholds']]
        for setting in grid:
            selected=choose(prediction,setting,members);after=cal['scores'][np.arange(len(selected)),selected];rates=[float(w@((after[:,c]<1).astype(float)-(base[:,c]<1).astype(float))) for c in [1,2]];rates.append(float(w@((after[:,0]==0).astype(float)-(base[:,0]==0).astype(float))));gain=float(w@(after[:,0]-base[:,0]));candidates[method].append(dict(setting=setting,pdms_gain=gain,net_collision=rates[0],net_offroad=rates[1],net_zero=rates[2],safe=all(v<=1e-12 for v in rates),active_fraction=float(w@(selected>0))))
    # Single-member algebra is exactly the previous rule, not a linearity claim about behavior.
    one=dict(method='mean',beta=0.,risk_penalty=members[0]['risk_penalty'],threshold=members[0]['threshold']);assert np.array_equal(choose(prediction[:,:1],one,members[:1]),choices(prediction[:,0],one['risk_penalty'],one['threshold']))
    configs={}
    for method,grid in candidates.items():
        eligible=[a for a in grid if a['safe']] if task['role']=='safety' else grid;assert eligible;best=max(eligible,key=lambda a:(a['pdms_gain'],-a['active_fraction']));folder=ROOT/'critic_ensemble_policies'/task['id']/method;path=folder/'POLICY.json'
        policy=dict(status='CALIBRATED_BEFORE_HELD_OUTCOMES',time=stamp(),system=task['system'],role=task['role'],heldout_fold=held,K=len(parts),kind='critic_ensemble_complete_candidate_selector',context_view=task['context'],source_family=task['source_kind'],members=members,member_policies=task['members'],parts=parts,setting=best['setting'],selected_calibration=best,candidates=grid,protocol=task['protocol'],protocol_sha256=task['protocol_sha256'],calibration_cases=len(set(indices.tolist())),calibration_sources=cal_sources,zero_expert_exact=True,no_hidden_or_trajectory_linear_mix=True)
        assert not path.exists();atomic(path,policy);configs[method]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path),policy=policy)
    if task.get('calibration_only'):
        assert held==-1;return dict(policies={m:dict(path=c['path'],sha256=c['sha256']) for m,c in configs.items()},held_outcomes_opened=False)
    # All selection/configuration artifacts above exist before held true scores are opened.
    hp=[];hd=None;held_sources=[]
    for spec,p in zip(task['members'],policies):
        point=read(ROOT/spec['held_point']);assert point['critics'][0]['checkpoint']==p['critic']['checkpoint'];d,lineage=matrices(point,spec['held_stage']);assert d['predicted'].shape[1]==1;hp.append(d['predicted'][:,0]);held_sources.extend(lineage)
        if hd is None:hd=d
        else:assert all(np.array_equal(hd[k],d[k]) for k in ['global_indices','seeds','scores','trajectory'])
    prediction=np.stack(hp,axis=1);ii=hd['global_indices'];nn=hd['seeds'];assert all(rows[int(i)]['subset']=='exploration' and int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5==held for i in ii);unique=sorted(set(ii.tolist()));noises=sorted(set(nn.tolist()));assert noises==[0,1,2];ip={v:j for j,v in enumerate(unique)};npair={v:j for j,v in enumerate(noises)};out=[]
    for method,config in configs.items():
        selected=choose(prediction,config['policy']['setting'],members);after=hd['scores'][np.arange(len(selected)),selected];base=hd['scores'][:,0];score=np.full((len(unique),2,3,7),np.nan);seen=set()
        for j,(i,n) in enumerate(zip(ii,nn)):
            key=(ip[int(i)],npair[int(n)]);assert key not in seen;seen.add(key);score[key[0],0,key[1]]=base[j];score[key[0],1,key[1]]=after[j]
        assert np.isfinite(score).all();ident=task['id']+'_'+method;folder=ROOT/('analysis/critic_ensemble_engineering/projections' if task.get('engineering') else 'analysis/responses/token_full_cv_projection_v1');matrix=folder/(ident+'.npz');hashed=save_npz(matrix,global_indices=np.asarray(unique),seeds=np.asarray(noises),arm_ids=np.asarray(['baseline',task['role']]),scores=score);point=ROOT/('analysis/critic_ensemble_engineering/points' if task.get('engineering') else 'analysis/token_cv_points')/(ident+'.json');atomic(point,dict(id=ident,system=task['system'],heldout_fold=held,mode='heldout',kind='wave1',panel=unique,seeds=noises,ensemble_policy=config['path'],ensemble_policy_sha256=config['sha256'],member_fit_seeds=[2026101801,2026101802,2026101803],zero_expert_available=True))
        meta=folder/(ident+'.json');atomic(meta,dict(status='COMPLETE',time=stamp(),source_mode='heldout',task=dict(stage='runs/token_ensemble_'+task['source_kind']+'_'+method+'_cv_v1'),point=str(point.relative_to(ROOT)),matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,policy=config['path'],policy_sha256=config['sha256'],held_outcomes_used_after_policy_freeze=True,actual_outcomes_reused=True,source_predictions=held_sources,validation_accessed=False,test_accessed=False));out.append(dict(method=method,path=str(meta.relative_to(ROOT)),policy=config['path']))
    proof=ROOT/'analysis/critic_ensembles'/task['id']/'SUMMARY.json';atomic(proof,dict(status='CPU_ONLY_EXACT_CANDIDATE_SELECTION_COMPLETE',time=stamp(),task=task,outputs=out,three_readout_fits_same_expert_bank=True,whole_system_fit_repeats_not_replaced=True,new_model_or_trajectory_or_scoring_runs=0,zero_identity_and_single_member_rule_checked=True));return dict(path=str(proof.relative_to(ROOT)),outputs=out)
