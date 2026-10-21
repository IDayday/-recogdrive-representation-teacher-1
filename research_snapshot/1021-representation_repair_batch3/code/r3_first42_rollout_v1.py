"""All-quality paired first42 execution with actual same-forward interface targets.

The raw VLM is evaluated once per scene, then exact frozen suffixes and five
paired noise draws. Inputs are prefetched and independent scoring overlaps the
next scene. Only byte-identical executable aliases reuse a complete execution.
"""
from r3_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import uuid


@lru_cache(maxsize=4)
def loaded(path,hashed):
    assert sha(path)==hashed
    return read(path)


class FitBank:
    def __init__(self):self.data={}
    def get(self,root,arm):
        import numpy as np
        import torch
        path=Path(root)/arm['fit_path'];key=(str(path),arm['fit_sha256'])
        if key not in self.data:
            assert sha(path)==key[1]
            with np.load(path,allow_pickle=False) as z:
                self.data[key]={k:torch.as_tensor(np.array(z[k]),device='cuda',dtype=torch.float32) for k in z.files}
        return self.data[key]


BANK=None


@lru_cache(maxsize=8)
def gate_fit(path,hashed):
    import numpy as np
    assert sha(path)==hashed
    with np.load(path,allow_pickle=False) as z:return {k:np.asarray(z[k],dtype=np.float64) for k in ['center','basis','mh','mf','cov_inv_s','cov_inv_f']}


def observation_gate(engine,root,arm):
    import numpy as np
    from vlm_core import VISION_GROUPS,LANGUAGE_GROUPS
    gate=arm['observation_gate'];fit=gate['fit'];block=fit['block'];group=fit['group']
    matrix,_=engine.vm if block.startswith('vision') else engine.bm if block.startswith('bridge') else engine.lm
    names=VISION_GROUPS if block.startswith(('vision','bridge')) else LANGUAGE_GROUPS
    value=(matrix[names.index(group)]@engine.prefix[block].reshape(-1,engine.prefix[block].shape[-1]).float()).detach().cpu().numpy().astype(np.float64)
    z=gate_fit(str(Path(root)/fit['path']),fit['sha256']);p=(value-z['center'])@z['basis'];ds=p-z['mh'];df=p-z['mf']
    risk=.5*(ds@z['cov_inv_s']@ds-df@z['cov_inv_f']@df)
    return bool(np.isfinite(risk) and risk>gate['threshold']),float(risk)


def select(records,entries):
    """No evaluation-noise feedback can affect the R3 choice."""
    import numpy as np
    scores=np.asarray([[r['score']['score'] for r in records if r['arm']==e['id']] for e in entries],dtype=np.float64)
    assert scores.shape==(len(entries),5) and np.isfinite(scores).all()
    byid={r['arm']:r['relative_edit'] for r in records}
    def winner(values):
        high=values.max();equal=np.flatnonzero(values==high)
        return min(equal,key=lambda i:(entries[i]['id']!='Base',byid[entries[i]['id']],entries[i]['id']))
    r1=[int(winner(scores[:,j])) for j in range(5)];r2=int(winner(scores.mean(1)));r3=int(winner(scores[:,:3].mean(1)))
    return dict(R1=[dict(arm=entries[i]['id'],seed_index=j) for j,i in enumerate(r1)],
                R2=[dict(arm=entries[r2]['id'],seed_index=j) for j in range(5)],
                R3=[dict(arm=entries[r3]['id'],seed_index=j) for j in [3,4]],
                R3_selection_seeds=[0,1,2],R3_evaluation_seeds=[3,4],R3_negative_evaluation_retained=True)


def save_arrays(path,arrays):
    import numpy as np
    import zipfile
    import io
    path=Path(path).resolve();assert path.is_relative_to(ROOT) and not path.exists()
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    # Level 1 keeps CPU compression from becoming the critical path.
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as output:
        for key,value in arrays.items():
            stream=io.BytesIO();np.lib.format.write_array(stream,np.asarray(value),allow_pickle=False);output.writestr(key+'.npy',stream.getvalue())
    temporary.replace(path)
    return sha(path)


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r3_runtime import prediction
    global BANK
    if BANK is None:BANK=FitBank()
    pack=loaded(task['pack'],task['pack_sha256']);rows=loaded(task['rows'],task['rows_sha256']);entries=pack['entries']
    assert len(entries)==42 and task['seeds']==[0,1,2,3,4]
    assert engine.planner_runtime['checkpoint_sha256']==pack['checkpoint_sha256']
    indices=task.get('indices',list(range(task.get('start',0),task.get('end',0))))
    began=time.monotonic();pending=[];completed=[]
    timing=dict(read_decode_seconds=0.,input_wait_seconds=0.,vlm_seconds=0.,candidate_seconds=0.,device_return_seconds=0.,score_wait_seconds=0.,write_seconds=0.)
    def fetch(index):
        start=time.monotonic();row=rows[index]
        return row,raw_features(row),baseline_row(row),time.monotonic()-start
    def finish(item):
        future,row,index,reference,interfaces,base_arrays,metrics=item;start=time.monotonic();records=future.result(timeout=3600);timing['score_wait_seconds']+=time.monotonic()-start
        assert len(records)==210 and {(r['arm'],r['seed_index']) for r in records}=={(e['id'],j) for e in entries for j in range(5)}
        base=next(r for r in records if r['arm']=='Base' and r['seed_index']==0);assert base['score']==reference['score']
        chosen=select(records,entries);needed={(r['arm'],r['seed_index']) for name in ['R1','R2','R3'] for r in chosen[name]}
        lookup={(r['arm'],r['seed_index']):r for r in records};selected={};targets={}
        for pair in sorted(needed):
            record=lookup[pair];key=record['interface_sha256'];selected[key]=interfaces[record['execution_key']]
            targets[pair[0]+'_S'+str(pair[1])]=dict(record,interface_array=key)
        output=ROOT/task['stage']/'cases'/row['token'];start=time.monotonic()
        arr=output/'teacher_interfaces.npz';interface_sha=save_arrays(arr,dict(selected,**base_arrays))
        path=output/'RESULT.json'
        atomic(path,dict(status='COMPLETE',time=stamp(),task_id=task['id'],global_index=index,token=row['token'],session=row['session'],subset=row.get('subset',task['cohort']),cohort=task['cohort'],
                         pack_sha256=task['pack_sha256'],records=records,selection=chosen,teacher_records=targets,
                         interfaces=dict(path=str(arr.relative_to(ROOT)),sha256=interface_sha,dtype='float32',site='action_head.feature_encoder output after intervention',same_actual_execution=True),
                         actual_token_positions_saved=True,metric_sha256=reference['metric_sha256'],statistics=metrics,
                         no_external_failure_gate=True,no_extra_safety_filter=True,R3_evaluation_not_used_for_selection=True))
        timing['write_seconds']+=time.monotonic()-start;completed.append(dict(token=row['token'],global_index=index,path=str(path.relative_to(ROOT)),sha256=sha(path),records=210))
    with ThreadPoolExecutor(max_workers=1) as reader:
        upcoming=reader.submit(fetch,indices[0]) if indices else None
        for offset,index in enumerate(indices):
            output=ROOT/task['stage']/'cases'/rows[index]['token']/'RESULT.json'
            start=time.monotonic();row,features,reference,elapsed=upcoming.result();timing['input_wait_seconds']+=time.monotonic()-start;timing['read_decode_seconds']+=elapsed
            if offset+1<len(indices):upcoming=reader.submit(fetch,indices[offset+1])
            if output.exists():
                old=read(output);assert old['pack_sha256']==task['pack_sha256'] and old['status']=='COMPLETE'
                assert sha(ROOT/old['interfaces']['path'])==old['interfaces']['sha256']
                completed.append(dict(token=row['token'],global_index=index,path=str(output.relative_to(ROOT)),sha256=sha(output),records=210,resumed=True));continue
            memo={};interfaces={};labels=[];predictions=[];statistics=[];metadata=[]
            with torch.no_grad():
                start=time.monotonic();hidden=engine.forward_native(features);timing['vlm_seconds']+=time.monotonic()-start
                mask=engine.inputs['attention_mask'][0].bool();base_arrays=dict(valid_token_positions=torch.nonzero(mask).flatten().cpu().numpy(),input_ids=engine.inputs['input_ids'][0].cpu().numpy())
                start=time.monotonic()
                for entry in entries:
                    key=entry['execution_key'];arm=entry['arm'];extra={}
                    if key not in memo:
                        if arm is None:condition,post,stat=hidden,None,hidden.new_zeros(4)
                        else:
                            actual=arm
                            if arm['gate']=='external_observation_qda_hard':
                                active,risk=observation_gate(engine,entry['root'],arm);extra=dict(observation_gate_active=active,observation_gate_risk=risk)
                                actual=dict(arm,gate='none') if active else None
                            if actual is None:condition,post,stat=hidden,None,hidden.new_zeros(4)
                            else:
                                changed,stat=engine.edited(actual,BANK.get(entry['root'],actual));condition,post=engine.suffix(actual['block'],changed)
                        seq=[];first=None
                        for j in task['seeds']:
                            trajectory,interface=prediction(engine,features,condition,j,row['token'],post)
                            valid=interface[0,mask].float()
                            if first is None:first=valid
                            else:assert torch.equal(first,valid),'Interface unexpectedly depends on action sampling'
                            seq.append(trajectory)
                        memo[key]=(torch.stack(seq),stat,extra);interfaces[key]=first.cpu().numpy()
                    values,stat,extra=memo[key];predictions.extend(values.unbind());statistics.extend([stat]*5);labels.extend((entry['id'],j,key) for j in task['seeds']);metadata.extend([extra]*5)
                timing['candidate_seconds']+=time.monotonic()-start;start=time.monotonic()
                values=torch.stack(predictions).float().cpu().numpy();stats=torch.stack(statistics).float().cpu().numpy();timing['device_return_seconds']+=time.monotonic()-start
            assert np.array_equal(values[0],reference['trajectory']) and np.isfinite(values).all()
            interface_hash={key:hashlib.sha256(arr.tobytes()).hexdigest() for key,arr in interfaces.items()};records=[]
            for value,stat,(ident,j,key),extra in zip(values,stats,labels,metadata):
                relative=float(stat[0]/max(stat[1],1e-12));entry=next(e for e in entries if e['id']==ident)
                assert relative<=float(entry['arm']['cap'] if entry['arm'] else 0)+1e-6
                records.append(dict(arm=ident,seed_index=j,seed=seed(row['token'],j),trajectory=value.tolist(),relative_edit=relative,
                                    execution_key=key,interface_sha256=interface_hash[key],same_execution_interface=True,**extra))
            scoring=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records))
            pending.append((scoring,row,index,reference,interfaces,base_arrays,dict(unique_executions=len(memo),candidate_entries=42)))
            if len(pending)>=2:finish(pending.pop(0))
        for item in pending:finish(item)
    engine.verify_engine();result=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(result,dict(status='COMPLETE',time=stamp(),task=task,cases=completed,timing=timing,seconds=time.monotonic()-began,checkpoint_sha256=engine.planner_runtime['checkpoint_sha256']))
    return dict(path=str(result.relative_to(ROOT)),sha256=sha(result),cases=len(completed),records=len(completed)*210,seconds=time.monotonic()-began,timing=timing)
