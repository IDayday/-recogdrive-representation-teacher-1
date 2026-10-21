"""Compare already-scored expert feedback in the fitting pool and held scenes.

Descriptive mechanism audit, no fitting, rollout, selection or causal claim.
The expert-fitting pool is not asserted to equal the actually sampled gradient
rows. Outer training views repeat across folds and are never extra independent
cases. Own-K Oracle and forced individual experts remain separate.
"""
from r2_common import *
from collections import defaultdict
import re


def main():
    setup('expert_feedback_distribution')
    import numpy as np
    rows=read(read(ROOT/'manifests/data_source.json')['rows']);q=np.load(read(ROOT/'manifests/data_source.json')['quality'])
    sources=[];banks={};cache={};records=[];coverage=[]
    def matrix(path):
        path=str(path)
        if path not in cache:
            meta=read(ROOT/path);assert sha(ROOT/meta['matrix'])==meta['matrix_sha256']
            with np.load(ROOT/meta['matrix']) as z:arrays={k:np.array(z[k]) for k in ['global_indices','arm_ids','seeds','scores']}
            cache[path]=(meta,arrays);sources.append(dict(path=path,sha256=sha(ROOT/path),matrix=meta['matrix'],matrix_sha256=meta['matrix_sha256']))
        return cache[path]
    for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
        d=read(p)
        if d['mode']=='heldout':banks[d['system'],d['heldout_fold']]=(str(p.relative_to(ROOT)),d)
    configs=[('expert_library_selection','expert_library_S0_v1','expert_library_noise_v1'),('causal_library_selection','causal_library_S0_v1','causal_library_noise_v1'),('spatial_library_selection','spatial_library_S0_v1','spatial_library_noise_v1'),('unified_bcs_library_selection','unified_bcs_library_S0_v1','unified_bcs_library_noise_v1'),('capacity_replication_selection','capacity_replication_S0_v1','capacity_replication_noise_v1')]
    for folder,s0,noise in configs:
        for p in sorted((ROOT/'analysis'/folder).glob('*.json')):
            selection=read(p);system=selection['system'];held=selection['heldout_fold']
            if held<0 or not re.search(r'_K[23]_seed[0-2]$',system):continue
            # Predeclared bounded descriptive scope: allthree seeds for the
            # selected correctionK3/spatialK2, initialfit for the others.
            keep=system.endswith('_seed0') or system.startswith('correction_K3_') or system.startswith('correction_spatial_K2_') or '_capacity_' in system
            if not keep:continue
            trainpaths=['analysis/responses/'+name+'/'+p.name for name in [s0,noise]];heldbank=banks.get((system,held))
            missing=[path for path in trainpaths if not (ROOT/path).exists()]
            if heldbank is None:missing.append('complete held candidate bank')
            coverage.append(dict(system=system,heldout_fold=held,selection=str(p.relative_to(ROOT)),ready=not missing,missing=missing))
            if missing:continue
            sources.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
            byid={a['id']:a for a in selection['arms']}
            datasets=[('fitting_pool_S0',trainpaths[0]),('fitting_pool_S1S2',trainpaths[1]),('outer_held_S0S1S2',heldbank[0])]
            for role,parts in selection['policies'].items():
                own=[v for _,v in sorted(parts.items(),key=lambda v:int(v[0]))]
                for dataset,path in datasets:
                    meta,a=matrix(path);ii=a['global_indices'];ids=list(a['arm_ids']);seeds=list(a['seeds']);scores=a['scores'];assert np.isfinite(scores).all()
                    assert all(rows[int(i)]['subset']=='exploration' for i in ii)
                    folds=np.array([int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5 for i in ii])
                    assert np.all(folds==held) if dataset.startswith('outer_held') else np.all(folds!=held)
                    chosen=[0]+[ids.index(v) for v in own];actual=scores[:,chosen];base=actual[:,0]
                    pick=actual[:,:,:,0].argmax(1);oracle=np.stack([actual[np.arange(len(ii)),pick[:,n],n] for n in range(len(seeds))],axis=1)
                    outcomes=[(ident,actual[:,j+1],byid[ident]['kind']) for j,ident in enumerate(own)]+[('own_K_Oracle',oracle,'privileged')]
                    for quality,mask in [('S0_failure',q[ii]<.7),('S0_high',q[ii]>.9),('S0_intermediate',(q[ii]>=.7)&(q[ii]<=.9))]:
                        assert mask.any()
                        for ident,after,kind in outcomes:
                            for n,seed_index in enumerate(seeds):
                                b=base[mask,n];v=after[mask,n];delta=(v[:,0]-b[:,0])*100;detail=dict(system=system,heldout_fold=held,role=role,nominal_K=selection['K'],active_K=len(own),dataset=dataset,quality_class=quality,seed_index=int(seed_index),expert=ident,expert_kind=kind,cases=int(mask.sum()),sessions=len({rows[int(i)]['session'] for i in ii[mask]}),Base_mean_PDMS=float(b[:,0].mean()*100),after_mean_PDMS=float(v[:,0].mean()*100),mean_PDMS_gain=float(delta.mean()),median_gain=float(np.median(delta)),improved_count=int(np.sum(delta>1e-6)),damaged_count=int(np.sum(delta< -1e-6)),repair70_count=int(np.sum((b[:,0]<.7)&(v[:,0]>=.7))),repair90_count=int(np.sum((b[:,0]<.7)&(v[:,0]>.9))),lost_high_count=int(np.sum((b[:,0]>.9)&(v[:,0]<=.9))),high_to_failure_count=int(np.sum((b[:,0]>.9)&(v[:,0]<.7))))
                                for label,old,new in [('collision',b[:,1]<1,v[:,1]<1),('offroad',b[:,2]<1,v[:,2]<1),('zero',b[:,0]==0,v[:,0]==0),('TTC',b[:,3]<1,v[:,3]<1)]:
                                    detail['new_'+label]=int(np.sum(~old&new));detail['removed_'+label]=int(np.sum(old&~new))
                                records.append(detail)
    assert records
    # Fivefold summaries are simple descriptive means of completefold rows,
    # not a naturalpopulation estimate or a new hypothesis test.
    groups=defaultdict(list)
    for r in records:
        if r['expert']=='own_K_Oracle':groups[(r['system'],r['role'],r['dataset'],r['quality_class'],r['seed_index'])].append(r)
    summaries=[]
    for key,values in sorted(groups.items()):
        count=sum(r['cases'] for r in values);summaries.append(dict(system=key[0],role=key[1],dataset=key[2],quality_class=key[3],seed_index=key[4],folds=sorted(r['heldout_fold'] for r in values),complete_fivefold={r['heldout_fold'] for r in values}==set(range(5)),case_views=count,mean_PDMS_gain=sum(r['mean_PDMS_gain']*r['cases'] for r in values)/count,improved_fraction=sum(r['improved_count'] for r in values)/count,damaged_fraction=sum(r['damaged_count'] for r in values)/count))
    directory=ROOT/'analysis/expert_feedback_distribution'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f');directory.mkdir(parents=True,exist_ok=False)
    summary=dict(status='DESCRIPTIVE_EXISTING_EXPERT_FEEDBACK_DISTRIBUTION_AUDIT',time=stamp(),coverage=coverage,records=records,own_K_Oracle_summaries=summaries,sources=sources,
        scope='Already available complete trainingpool/outerheld candidate matrix pairs only. K2/3, predefined seed scope; partialfold coverage explicit. S0 quality classes retained across noises. Fittingpool doesnot prove every row was sampled for expert gradientupdates; routeinnercalibration may exclude criticfitting but not expertfitting. Trainingviews repeat across outerfolds. No newindependent cases, significance, causaloverfitting or informationimpossibility claim.',
        limitations=['Different scenes andsample sizes across fittingpool/held sets; this contrast alone cannot isolate memorization from covariateshift or training-setsize effects.','Own-K Oracle is privileged; forced experts and all safetycosts separately preserved.','A truly cross-fitted feedback learner requires a separate protocol; this audit doesnot claim that control has been run.'],
        new_model_training=0,new_rollouts=0,new_scoring=0,validation_accessed=False,test_accessed=False)
    atomic(directory/'SUMMARY.json',summary);atomic(ROOT/'analysis/expert_feedback_distribution/LATEST.json',dict(time=stamp(),path=str((directory/'SUMMARY.json').relative_to(ROOT)),sha256=sha(directory/'SUMMARY.json')))
    print(json.dumps(dict(path=str((directory/'SUMMARY.json').relative_to(ROOT)),bankfold_pairs=sum(r['ready'] for r in coverage),candidate_pairs=len(coverage),rows=len(records),new_rollouts=0)))


if __name__=='__main__':main()
