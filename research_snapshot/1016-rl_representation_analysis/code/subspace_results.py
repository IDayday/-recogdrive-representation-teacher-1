"""Acceptance, full-family confirmation correction and compact evidence tables."""
from common import *
import argparse
import numpy as np
from subspace_scan_prepare import OUT
from subspace_scan_cv import fold_ids


def holm(values):
    p=np.array(values);order=np.argsort(p);q=np.empty(len(p));q[order]=np.maximum.accumulate(np.minimum(1.,p[order]*(len(p)-np.arange(len(p)))));return q


def main(args):
    setup('subspace_scan/results');cfg=read(ROOT/args.execution);base=ROOT/'runs'/cfg['run']
    assert (base/'CONFIRM_DRAINED_RESOURCES_HELD.json').exists();lock=read(OUT/'FROZEN_CONFIRMATION.json');tasks=read(base/'tasks.json')
    assert not read(base/'queue.json')['closed'];assert len({t['id'] for t in tasks})==len(tasks)
    assert {p.stem for p in (base/'receipts').glob('*.json')}=={t['id'] for t in tasks}
    assert {p.stem for p in (base/'results').glob('*.json')}=={t['id'] for t in tasks}
    for p,h in cfg['code_sha256'].items():assert sha(ROOT/p)==h,p
    assert sha(OUT/'PROTOCOL.json')==cfg['protocol_sha256']
    assert sha(OUT/'CV_SEARCH_LEDGER.npy')==lock['cv_search_ledger_sha256']
    cache=read(OUT/'CACHE_INDEX.json');assert len(cache['cells'])==3040
    for p,h in cache['proofs_sha256'].items():assert sha(ROOT/p)==h,p
    records=[];cv_count=0;fit_hashes={};effective={};total_variants=0
    for index,task in enumerate(tasks):
        path=base/'results'/(task['id']+'.json');receipt=read(base/'receipts'/path.name);assert receipt['task']==task and sha(path)==receipt['result_sha256']
        doc=read(path);assert doc['status']=='COMPLETE' and doc['task']==task
        assert doc['cache_sha256']==cache['cells'][doc['cell']]['sha256']
        if task['phase']=='cv':
            cv_count+=1;assert not doc['heldout_validation_evaluated'];assert len(doc['search'])==1346;total_variants+=len(doc['search'])
            if task['route']=='r1':assert doc['full_moment_reuse_verified_all_dimensions']
            key=task['route'];e=effective.setdefault(key,dict(requested=0,valid=0,rank_ineligible=0,constant_or_insufficient=0,cutoff_degenerate=0))
            for r in doc['search']:
                e['requested']+=1
                if r['status']=='VALID':e['valid']+=1;e['cutoff_degenerate']+=int(r['cutoff_degenerate_any_fold'])
                elif any(f['rank']['status']=='RANK_INELIGIBLE' for f in r['folds']):e['rank_ineligible']+=1
                else:e['constant_or_insufficient']+=1
        else:
            assert doc['selection_sha256']==sha(OUT/'FROZEN_CONFIRMATION.json') and doc['fixed_exploration_only_fits']
            for r in doc['results']:
                records.append(dict(cell=doc['cell'],route=task['route'],task=task,**r))
            for fit in doc['fits']:assert sha(ROOT/fit['path'])==fit['sha256'];fit_hashes[fit['path']]=fit['sha256']
        if index%128==0:print(json.dumps(dict(status='ACCEPT_RESULT_HASHES',completed=index,total=len(tasks))),flush=True)
    assert cv_count==3040
    assert len(records)==sum(len(v) for v in lock['cells'].values())
    # Correct all frozen contrasts, including controls and both P0/P1, per route.
    sizes={}
    for route in ['r1','r2']:
        family=[]
        for i,r in enumerate(records):
            if r['route']!=route:continue
            for group in (['P0'] if route=='r1' else ['P0','P1']):
                infer=r.get('inference_'+group);family.append((i,group,infer['p_one_sided_signflip'] if infer else 1.))
        q=holm([v[2] for v in family]);sizes[route]=len(family)
        for (i,group,p),adjusted in zip(family,q):records[i]['holm_'+group]=float(adjusted)
    regions=[]
    for region in lock['regions']:
        candidates=[r for r in records if r['cell']==region['cell'] and r['centering']==region['centering'] and r['index']==region['index']]
        assert len(candidates)==1;leader=candidates[0];neighbors=[r for r in records if r['cell']==region['cell'] and r['centering']==region['centering'] and r['index'] in region['neighbor_indices']]
        def positive(r):
            a=r.get('P0');b=r.get('P1');infer=r.get('inference_P0')
            passed=a is not None and infer is not None and not r['rank'].get('cutoff_degenerate',False) and a['auc']>=.6 and a['standardized_gap']>=.2 and infer['auc_ci95'][0]>.5 and r.get('holm_P0',1)<=.05
            if region['cell'].startswith('r2_'):passed=passed and b is not None and r.get('noise_consistency',{}).get('common_endpoint_pairs',0)>=20 and (r.get('noise_consistency',{}).get('common_branch_order_agreement') or 0)>=.7 and r.get('holm_P1',1)<=.05 and min(a.get('pair_ordering',0) or 0,b.get('pair_ordering',0) or 0)>=.6 and abs(a['pair_ordering']-b['pair_ordering'])<=.1
            return bool(passed)
        stable_neighbors=sum(positive(r) for r in neighbors)
        regions.append(dict(region_id=region['region_id'],route=leader['route'],cell=region['cell'],centering=region['centering'],
            equal_main=leader['config']['equal'],diagnostic_only=region['diagnostic_only'],leader=leader,
            neighboring_points=len(neighbors),positive_neighbors=stable_neighbors,leader_confirmed=positive(leader),
            stable_region_confirmed=not region['diagnostic_only'] and positive(leader) and stable_neighbors>=2,cv=region))
    splitproof={}
    for route,file in [('r1','natural_metadata.json'),('r2','paired_metadata.json')]:
        meta=read(OUT/file);fold=fold_ids(meta);exp=np.array([r['subset']=='exploration' for r in meta]);sessions=np.array([r['session'] for r in meta]);groups={str(k):sorted(set(sessions[exp&(fold==k)])) for k in range(5)};hold=set(sessions[~exp])
        assert not set(sessions[exp])&hold
        assert sum(len(v) for v in groups.values())==len(set(sessions[exp]));splitproof[route]=dict(fold_sessions=groups,validation_sessions=sorted(hold),exploration_cases=int(exp.sum()),validation_cases=int((~exp).sum()))
    atomic(OUT/'SPLIT_AUDIT.json',splitproof)
    atomic(OUT/'CONFIRMATION_RESULTS.json',dict(status='COMPLETE',time=stamp(),records=records,regions=regions,holm_family_sizes=sizes,effective_scope=effective,
        validation_confirmation_is_existing_navtrain_holdout=True,no_navtest_data_in_expanded_analysis=True,selection_sha256=sha(OUT/'FROZEN_CONFIRMATION.json')))
    states=[read(base/'workers'/f'rank{r:03d}.json') for r in range(2*cfg['workers_per_node'])];assert all(s['status']=='QUEUE_WAIT' for s in states)
    for rank in range(2*cfg['workers_per_node']):
        runtime=read(base/'runtime'/f'rank{rank:03d}.json');assert runtime['backend']==cfg['score_backend'] and not runtime['model_loaded']
        assert runtime['cpu_threads_per_worker']==cfg['cpu_threads_per_worker']
        assert all(r['num_threads']==cfg['cpu_threads_per_worker'] for r in runtime['threadpools'] if r['user_api']=='blas')
    from cloud_api import request
    jobs=[]
    for node in [0,1]:
        smoke=read(base/f'node{node}/SMOKE_PASS.json');assert smoke['status']=='PASS' and smoke['workers']==cfg['workers_per_node'] and smoke['physical_devices']==16
        job_id=read(ROOT/cfg['submissions'][node])['JobId'];j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job_id);assert j['Status']=='Running';jobs.append(dict(JobId=job_id,Status=j['Status']))
    result=dict(status='PASS',time=stamp(),run=cfg['run'],tasks=len(tasks),cv_cells=cv_count,requested_variants=total_variants,confirm_hypotheses=len(records),
        execution_sha256=sha(ROOT/args.execution),selection_sha256=sha(OUT/'FROZEN_CONFIRMATION.json'),all_result_hashes_and_coverage_checked=True,
        fits_sha256=fit_hashes,all_route1_full_moments_independently_checked=True,original_raw_sources_hash_checked=True,
        model_collection_rerun=False,resources_retained=True,workers_waiting=len(states),jobs=jobs,report_pending=True)
    atomic(OUT/'FINAL_ACCEPTANCE.json',result);atomic(base/'FINAL_ACCEPTANCE.json',result)
    print(json.dumps(dict(status='PASS',tasks=len(tasks),regions=len(regions),stable_confirmed=sum(r['stable_region_confirmed'] for r in regions))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',required=True);main(p.parse_args())
