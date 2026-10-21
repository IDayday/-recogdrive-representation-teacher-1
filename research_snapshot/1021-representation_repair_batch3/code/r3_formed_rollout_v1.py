"""Prepared full-coverage formed-candidate evaluator with bounded IO.

Inputs are prefetched; scoring overlaps the following scene. Raw branches,
scores and source identities are retained in compact numeric arrays. Actual
interfaces are exported for local winners that can compete with first42.
This file is not admitted for formal use until its multidevice checks pass.
"""
from r3_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


@lru_cache(maxsize=8)
def document(path,expected):
    assert sha(path)==expected
    return read(path)


@lru_cache(maxsize=3)
def prior(summary_path,expected):
    import numpy as np
    summary=document(summary_path,expected)
    assert summary['status'] in ['PASS_COMPLETE_AUDITED_FIRST42','PASS_ENGINEERING_ONLY']
    arrays={name:np.load(ROOT/summary['artifacts'][name+'.npy']['path'],mmap_mode='r',allow_pickle=False)
            for name in ['scores','trajectories']}
    assert arrays['scores'].shape[1:]==(42,5,7) and arrays['trajectories'].shape[1:]==(42,5,8,3)
    return summary,arrays


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r3_formed_scene_v2 import Scene
    from r3_inference_cache_v2 import constant_context
    from r3_first42_rollout_v2 import save_arrays
    from r3_select_generic_v1 import select
    from r3_incremental_audit_v1 import FIELDS
    pack=document(task['pack'],task['pack_sha256']);rows=document(task['rows'],task['rows_sha256'])
    reference_summary,tables=prior(task['first42_summary'],task['first42_summary_sha256'])
    assert task['seeds']==[0,1,2,3,4] and pack['candidate_scope']=='formed'
    assert pack['checkpoint_sha256']==engine.planner_runtime['checkpoint_sha256']
    assert reference_summary['rows_sha256']==task['rows_sha256']
    assert reference_summary['cohort']==task['cohort']
    if not task.get('engineering',False):
        assert reference_summary['status']=='PASS_COMPLETE_AUDITED_FIRST42'
        assert (ROOT/'teachers/first42_v1/FROZEN.json').exists()
        admission=document(pack['runtime_admission'],pack['runtime_admission_sha256'])
        assert admission['status']=='PASS_FORMED_RUNTIME_MULTI_DEVICE'
        if task['cohort']=='navtest':
            lock=document(task['test_lock'],task['test_lock_sha256'])
            assert lock['status']=='FROZEN_BEFORE_TEST' and lock['pack_sha256']==task['pack_sha256'] and lock['test_rows_sha256']==task['rows_sha256']
    entries=[dict(id='Base',kind='Base',definition={})]+pack['entries'];order=[e['id'] for e in entries]
    assert len(order)==len(set(order))
    pending=[];completed=[];began=time.monotonic()
    timing=dict(read_decode_seconds=0.,input_wait_seconds=0.,inference_seconds=0.,device_return_seconds=0.,score_wait_seconds=0.,write_seconds=0.)

    def fetch(index):
        start=time.monotonic();row=rows[index]
        oldq=np.asarray(tables['scores'][index]);oldt=np.asarray(tables['trajectories'][index,0])
        assert np.isfinite(oldq).all() and np.isfinite(oldt).all()
        if task['cohort']=='navtrain':metric_sha=baseline_row(row)['metric_sha256']
        else:metric_sha=row.get('metric_sha256') or sha(row['metric_cache'])
        return row,raw_features(row),oldq,oldt,metric_sha,time.monotonic()-start

    def finish(item):
        future,row,index,oldq,branches,base_arrays,mask,cache_stats=item
        start=time.monotonic();records=future.result(timeout=3600);timing['score_wait_seconds']+=time.monotonic()-start
        assert len(records)==len(entries)*5
        lookup={(r['arm'],r['seed_index']):r for r in records};assert len(lookup)==len(records)
        for j in range(5):assert [lookup['Base',j]['score'][f] for f in FIELDS]==oldq[0,j].tolist()
        q=np.asarray([[[lookup[ident,j]['score'][f] for f in FIELDS] for j in range(5)] for ident in order],dtype=np.float64)
        assert q.shape==(len(order),5,7) and np.isfinite(q).all() and (q>=0).all() and (q<=1+1e-8).all()
        assert np.max(np.abs(q[:,:,1]*q[:,:,2]*(5*q[:,:,4]+5*q[:,:,3]+2*q[:,:,5])/12-q[:,:,0]))<1e-8
        chosen=select(records,order);needed=set()
        # First42 is a fixed lower bound on every later accepted union. Preserve
        # ties conservatively unless the bound is already attained by Base.
        oldscore=oldq[:,:,0]
        for item in chosen['R1']:
            ident,j=item['arm'],item['seed_index'];value=lookup[ident,j]['score']['score'];bound=oldscore[:,j].max()
            if ident!='Base' and (value>bound or (value==bound and oldscore[0,j]<bound)):needed.add((ident,j))
        for endpoint,noise in [('R2',range(5)),('R3',range(3))]:
            ident=chosen[endpoint][0]['arm'];use=list(noise)
            value=np.mean([lookup[ident,j]['score']['score'] for j in use]);bounds=oldscore[:,use].mean(1);bound=bounds.max()
            if ident!='Base' and (value>bound or (value==bound and bounds[0]<bound)):
                needed.update((ident,j) for j in range(5))
        arrays={};exports={}
        for pair in sorted(needed):
            branch=branches[pair];h=branch.interface[0,mask].float().cpu().numpy()
            assert h.dtype==np.float32 and h.shape==(len(base_arrays['valid_token_positions']),384) and np.isfinite(h).all()
            hashed=hashlib.sha256(h.tobytes()).hexdigest();arrays[hashed]=h
            exports[pair[0]+'_S'+str(pair[1])]=dict(lookup[pair],interface_array=hashed,interface_sha256=hashed,
                 actual_source=branch.source,router_diagnostic=branch.diagnostic,same_execution_interface=True)
        t=np.asarray([[lookup[ident,j]['trajectory'] for j in range(5)] for ident in order],dtype=np.float32)
        edits=np.asarray([[lookup[ident,j]['relative_edit'] for j in range(5)] for ident in order],dtype=np.float64)
        sources=np.asarray([[branches[ident,j].source for j in range(5)] for ident in order])
        output=ROOT/task['stage']/'cases'/row['token'];start=time.monotonic()
        numeric=output/'branches.npz';numeric_sha=save_arrays(numeric,dict(scores=q,trajectories=t,relative_edits=edits,actual_sources=sources))
        interfaces=output/'teacher_interfaces.npz';interface_sha=save_arrays(interfaces,dict(arrays,**base_arrays))
        path=output/'RESULT.json'
        atomic(path,dict(status='COMPLETE',time=stamp(),task_id=task['id'],global_index=index,token=row['token'],session=row['session'],subset=row.get('subset',task['cohort']),
            cohort=task['cohort'],pack_sha256=task['pack_sha256'],candidate_ids=order,fields=FIELDS,seeds=[0,1,2,3,4],
            numeric=dict(path=str(numeric.relative_to(ROOT)),sha256=numeric_sha),interfaces=dict(path=str(interfaces.relative_to(ROOT)),sha256=interface_sha),
            selection=chosen,teacher_records=exports,interface_retention='Actual local winners competitive with immutable first42 lower bound; Base targets remain in first42',
            all_R3_selected_policy_noise_targets_retained_if_competitive=True,cache_statistics=cache_stats,
            no_external_failure_gate=True,no_extra_safety_filter=True,R3_evaluation_not_used_for_selection=True,
            prior_summary_sha256=task['first42_summary_sha256'],base_all_five_trajectories_and_scores_exact=True))
        timing['write_seconds']+=time.monotonic()-start
        completed.append(dict(token=row['token'],global_index=index,path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(order)*5))

    with ThreadPoolExecutor(max_workers=1) as reader:
        indices=task['indices'];upcoming=reader.submit(fetch,indices[0]) if indices else None
        for offset,index in enumerate(indices):
            start=time.monotonic();row,features,oldq,oldt,metric_sha,read_seconds=upcoming.result()
            timing['input_wait_seconds']+=time.monotonic()-start;timing['read_decode_seconds']+=read_seconds
            if offset+1<len(indices):upcoming=reader.submit(fetch,indices[offset+1])
            output=ROOT/task['stage']/'cases'/row['token']/'RESULT.json'
            if output.exists():
                d=read(output);assert d['status']=='COMPLETE' and d['pack_sha256']==task['pack_sha256']
                for key in ['numeric','interfaces']:assert sha(ROOT/d[key]['path'])==d[key]['sha256']
                completed.append(dict(token=row['token'],global_index=index,path=str(output.relative_to(ROOT)),sha256=sha(output),records=len(order)*5,resumed=True));continue
            branches={};annotations=[];predictions=[];start=time.monotonic()
            with torch.no_grad(),constant_context(engine) as cache_stats:
                scene=Scene(engine,features,row['token']);mask=engine.inputs['attention_mask'][0].bool()
                base_arrays=dict(valid_token_positions=torch.nonzero(mask).flatten().cpu().numpy(),input_ids=engine.inputs['input_ids'][0].cpu().numpy())
                for entry in entries:
                    for j in range(5):
                        branch=scene.evaluate(entry,j);branches[entry['id'],j]=branch;predictions.append(branch.trajectory)
                        annotations.append(dict(arm=entry['id'],seed_index=j,seed=seed(row['token'],j),relative_edit=branch.relative_edit))
                timing['inference_seconds']+=time.monotonic()-start;start=time.monotonic()
                values=torch.stack(predictions).float().cpu().numpy();timing['device_return_seconds']+=time.monotonic()-start
            assert values.shape==(len(order)*5,8,3) and np.isfinite(values).all() and np.array_equal(values[:5],oldt)
            records=[dict(label,trajectory=value.tolist()) for label,value in zip(annotations,values)]
            future=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=metric_sha,scoring=engine.cfg['scoring'],records=records))
            pending.append((future,row,index,oldq,branches,base_arrays,mask,cache_stats))
            if len(pending)>=2:finish(pending.pop(0))
        for item in pending:finish(item)
    engine.verify_engine();result=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(result,dict(status='COMPLETE',time=stamp(),task=task,cases=completed,timing=timing,seconds=time.monotonic()-began,
                      actual_fresh_generation_and_independent_scoring=True,formal_use_requires_multi_device_admission=True))
    return dict(path=str(result.relative_to(ROOT)),sha256=sha(result),cases=len(completed),records=len(completed)*len(order)*5,seconds=time.monotonic()-began,timing=timing)
