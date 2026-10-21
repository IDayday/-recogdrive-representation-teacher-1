"""Paired complete-panel analysis for quality/random/full control directions.

All comparisons use identical scenes, perturbation norm cap, optimizer steps and
true-score selection opportunities. The dimension changes, so this is a finite
optimizer comparison rather than proof of a mathematical upper bound.
"""
from r2_common import *


def run(task):
    import numpy as np
    from r2_point_response import FIELDS
    from r2_expert_space import save_npz
    stage=ROOT/task['stage'];assert sha(stage/'tasks.json')==task['tasks_sha256'];tasks=read(stage/'tasks.json');protocol=read(ROOT/'config/SPACE_CONTROLLABILITY_PROTOCOL_V1.json');panel=protocol['panel'];groups={};lineage=[]
    for t in tasks:
        receipt=read(stage/'receipts'/(t['id']+'.json'));assert receipt['task']==t and t['steps']==24
        basis=t.get('basis',{});config=basis.get('config',{});spec=dict(block=t['block'],cap=t['cap'],rank=t['rank'],space=t['space'],basis_id=basis.get('id'),basis_config=config);key=digest(spec)
        group=groups.setdefault(key,dict(spec=spec,cases={}))
        for entry in receipt['result']['records']:
            path=ROOT/entry['path'];d=read(path);assert d['task']==t and d['index'] in panel and d['index'] not in group['cases'];assert d['actual_rank']==t['rank'] and d['privileged'] and not d['deployable'];records=d['records'];assert [v['iteration'] for v in records[:-1]]==[0,4,8,12,16,20,24];assert d['selected_index']==max(range(7),key=lambda j:records[j]['score']['score'])
            base=[records[0]['score']];after=[records[d['selected_index']]['score']]
            for noise in [1,2]:
                base.append(next(v['score'] for v in d['transfer'] if v['arm']=='baseline' and v['seed_index']==noise));after.append(next(v['score'] for v in d['transfer'] if v['arm']=='selected_on_S0' and v['seed_index']==noise))
            base=np.array([[a[f] for f in FIELDS] for a in base]);after=np.array([[a[f] for f in FIELDS] for a in after]);assert np.isfinite(base).all() and np.isfinite(after).all() and np.all(base[:,0]<.7);assert records[-1]['score']['score']>.9;assert after[0,0]>=base[0,0]
            edit=records[d['selected_index']]['relative_edit'];assert edit<=t['cap']+1e-5
            group['cases'][d['index']]=dict(base=base,after=after,session=d['session'],edit=edit,selected_iteration=records[d['selected_index']]['iteration'],seconds=d['seconds']);lineage.append(dict(path=entry['path'],sha256=sha(path)))
    keys=sorted(groups);assert len(keys)==100;assert all(set(g['cases'])==set(panel) for g in groups.values());reference=groups[keys[0]]['cases'];sessions=sorted({reference[i]['session'] for i in panel});membership=np.array([sessions.index(reference[i]['session']) for i in panel]);cluster_counts=np.bincount(membership,minlength=len(sessions));base=np.stack([reference[i]['base'] for i in panel]);all_after=[];results=[]
    for key in keys:
        group=groups[key];spec=group['spec'];cases=group['cases'];assert all(np.array_equal(cases[i]['base'],reference[i]['base']) for i in panel);after=np.stack([cases[i]['after'] for i in panel]);delta=(after[:,:,0]-base[:,:,0])*100;all_after.append(after)
        results.append(dict(id=key,**spec,cases=len(panel),Base_mean_PDMS_by_noise=(base[:,:,0].mean(0)*100).tolist(),repaired_mean_PDMS_by_noise=(after[:,:,0].mean(0)*100).tolist(),gain_by_noise=delta.mean(0).tolist(),mean_transfer_gain=float(delta[:,1:].mean()),repair_over90_by_noise=np.sum(after[:,:,0]>.9,axis=0).tolist(),repair_atleast70_by_noise=np.sum(after[:,:,0]>=.7,axis=0).tolist(),net_collision_by_noise=(np.sum(after[:,:,1]<1,axis=0)-np.sum(base[:,:,1]<1,axis=0)).tolist(),net_offroad_by_noise=(np.sum(after[:,:,2]<1,axis=0)-np.sum(base[:,:,2]<1,axis=0)).tolist(),net_zero_by_noise=(np.sum(after[:,:,0]==0,axis=0)-np.sum(base[:,:,0]==0,axis=0)).tolist(),mean_selected_relative_edit=float(np.mean([cases[i]['edit'] for i in panel])),max_selected_relative_edit=float(max(cases[i]['edit'] for i in panel)),mean_selected_iteration=float(np.mean([cases[i]['selected_iteration'] for i in panel])),mean_case_seconds=float(np.mean([cases[i]['seconds'] for i in panel]))))
    all_after=np.stack(all_after);lookup={r['id']:j for j,r in enumerate(results)};comparisons=[];endpoint_columns=[]
    for a in results:
        if a['space']=='full':continue
        partners=[r for r in results if r['block']==a['block'] and r['cap']==a['cap'] and (r['space']=='full' or (a['space']!='Haar_random' and r['space']=='Haar_random' and r['rank']==a['rank']))]
        for b in partners:
            # a minus b: quality/random versus full, or quality versus one matched random replicate.
            diff=(all_after[lookup[a['id']],:,:,0]-all_after[lookup[b['id']],:,:,0])*100;endpoint=np.stack([diff[:,0],diff[:,1:].mean(1)],axis=1);first=len(endpoint_columns);endpoint_columns.extend([endpoint[:,0],endpoint[:,1]])
            comparisons.append(dict(left=a['id'],right=b['id'],type='same_rank_quality_minus_random' if b['space']=='Haar_random' else 'subspace_minus_channel_full',difference_by_noise=diff.mean(0).tolist(),mean_transfer_difference=float(diff[:,1:].mean()),_columns=[first,first+1]))
    endpoints=np.stack(endpoint_columns,axis=1);ss=np.zeros((len(sessions),endpoints.shape[1]))
    for j,c in enumerate(membership):ss[c]+=endpoints[j]
    observed=endpoints.mean(0);rng=np.random.default_rng(2026101829);B=10000;P=19999;boot=[];extreme=np.zeros(endpoints.shape[1],dtype=int)
    for start in range(0,B,250):
        n=min(250,B-start);pick=rng.integers(len(sessions),size=(n,len(sessions)));boot.append(ss[pick].sum(1)/cluster_counts[pick].sum(1)[:,None])
    boot=np.concatenate(boot)
    for start in range(0,P,500):
        n=min(500,P-start);sign=rng.integers(2,size=(n,len(sessions)))*2-1;value=sign@ss/len(panel);extreme+=np.sum(np.abs(value)>=np.abs(observed)[None]-1e-12,axis=0)
    raw=(extreme+1)/(P+1);adjusted=np.zeros(len(raw));previous=0.
    for rank,k in enumerate(np.argsort(raw)):previous=max(previous,min(1.,(len(raw)-rank)*raw[k]));adjusted[k]=previous
    for item in comparisons:
        values=[]
        for name,k in zip(['S0_selected','S1S2_fixed_delta_transfer'],item.pop('_columns')):values.append(dict(endpoint=name,mean_difference=float(observed[k]),session_bootstrap95=np.quantile(boot[:,k],[.025,.975]).tolist(),approximate_session_signflip_p=float(raw[k]),Holm_p=float(adjusted[k])))
        item['paired_statistics']=values
    folder=ROOT/'analysis/space_control_summary'/task['id'];folder.mkdir(parents=True,exist_ok=False);matrix=folder/'paired_scores.npz';hashed=save_npz(matrix,global_indices=np.asarray(panel),base_scores=base,selected_scores=all_after,group_ids=np.asarray(keys))
    record=dict(status='COMPLETE_BOUNDED_PRIVILEGED_MECHANISM_DIAGNOSTIC',time=stamp(),task=task,protocol_sha256=sha(ROOT/'config/SPACE_CONTROLLABILITY_PROTOCOL_V1.json'),release_sha256=sha(ROOT/'config/MECHANISM_DIAGNOSTICS_RELEASE.json'),case_configurations=len(lineage),groups=len(results),cases=len(panel),sessions=len(sessions),panel=panel,results=results,paired_comparisons=comparisons,matrix=str(matrix.relative_to(ROOT)),matrix_sha256=hashed,sources=lineage,
        scope='24 predeclared exploration-fold0 observed-all3-failure scenes with actualGT>90. Shared channel shift at interface_pre/post, not arbitrary tokenwise full hidden space. Qualityks=kf128 slice and ranks8/32/128. Not natural population performance or deployment gain.',
        multiplicity=dict(hypotheses=len(raw),comparison_family='Every same-rank quality versus each of two random replicas and every restricted subspace versus full, across both sites/caps and bothS0/transfer endpoints, including negative effects.',bootstrap_samples=B,signflip_samples=P),
        interpretation='Effect magnitude and fixed-delta cross-noise transfer take precedence over isolated significance. Each quality-versus-random pair is opportunity-matched; max over six quality bases is not compared as matched against max over two random bases. Full uses equal finite optimizer budget and need not achieve a mathematical optimum.',validation_accessed=False,test_accessed=False)
    atomic(folder/'SUMMARY.json',record);atomic(ROOT/'analysis/space_control_summary/LATEST.json',dict(time=stamp(),path=str((folder/'SUMMARY.json').relative_to(ROOT)),sha256=sha(folder/'SUMMARY.json')));return dict(path=str((folder/'SUMMARY.json').relative_to(ROOT)),groups=len(results),comparisons=len(comparisons))
