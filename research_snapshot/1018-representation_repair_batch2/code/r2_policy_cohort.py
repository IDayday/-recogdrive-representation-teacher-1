"""Run unchanged policy evaluators on shared scenes, project exact old records.

Only common input reads, native rollouts, and the evaluator's existing candidate
cache are shared. Each policy keeps its own expert set, decision and strength.
"""
from r2_common import *
from functools import lru_cache
import importlib.util

MODULES={}


@lru_cache(maxsize=2048)
def policy(path,hashed):
    assert sha(ROOT/path)==hashed
    return read(ROOT/path)


def components(point):
    out={}
    for spec in point['policies']:
        p=policy(spec['policy'],spec['policy_sha256'])
        for part in p['parts']:
            if part['kind']=='learned':key={k:part.get(k,1. if k=='strength' else None) for k in ['kind','training_task','checkpoint','strength']}
            elif part['kind']=='delta':key={k:part.get(k,1. if k=='strength' else None) for k in ['kind','fit','strength']}
            else:key=dict(kind=part['kind'],arm=part['arm'])
            signature=digest(key)
            if part['id'] not in out:out[part['id']]=signature
    return out


def execute(engine,entries,pool,stage,ident):
    assert entries
    first=read(ROOT/entries[0]['task']['point']);head=entries[0];t0=head['task'];panel=first['panel'][t0['start']:t0['end']]
    configs=[];mapping=[];known={}
    for j,entry in enumerate(entries):
        assert entry['handler']==head['handler'] and entry['handler_sha256']==head['handler_sha256']
        point=read(ROOT/entry['task']['point']);t=entry['task'];assert point['panel'][t['start']:t['end']]==panel and point['mode']==first['mode'] and point['seeds']==first['seeds']
        for key,value in components(point).items():
            assert key not in known or known[key]==value,('Different operators share ID',key)
            known[key]=value
        aliases={}
        for spec in point['policies']:
            alias='entry'+str(j)+'__'+spec['id'];assert spec['id']!='baseline';aliases[spec['id']]=alias;configs.append(dict(spec,id=alias))
        mapping.append((entry,point,aliases))
    physicalpoint=dict(first,id=ident,policies=configs,panel=panel,logical_cohort=True)
    pointpath=ROOT/stage/'points'/(ident+'.json');assert not pointpath.exists();atomic(pointpath,physicalpoint)
    source=ROOT/head['handler'];assert sha(source)==head['handler_sha256'];key=head['handler_sha256']
    if key not in MODULES:
        spec=importlib.util.spec_from_file_location('cohort_unchanged_'+key,source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);MODULES[key]=module
    result=MODULES[key].run(engine,dict(id=ident,stage=stage,point=str(pointpath.relative_to(ROOT)),start=0,end=len(panel)),pool)
    assert sha(ROOT/result['path'])==result['sha256'];raw=read(ROOT/result['path']);lookup={};tokens=[]
    for record in raw['records']:
        token=record['token']
        if token not in tokens:tokens.append(token)
        record_key=(token,record['arm'],record['seed_index']);assert record_key not in lookup;lookup[record_key]=record
    projections=[]
    for entry,point,aliases in mapping:
        order=['baseline'];parts=set()
        for spec in point['policies']:
            if entry['handler']=='code/r2_candidate_eval.py':
                p=policy(spec['policy'],spec['policy_sha256'])
                for part in p['parts']:
                    if part['id'] not in parts:order.append('candidate_'+part['id']);parts.add(part['id'])
            order.append(spec['id'])
        output=[]
        for token in tokens:
            for arm in order:
                physical=aliases.get(arm,arm)
                for noise in point['seeds']:output.append(dict(lookup[(token,physical,noise)],arm=arm))
        projections.append(dict(entry=entry,raw=dict(raw,task=entry['task'],records=output,seconds=0.,exact_cohort_projection=True,
            physical_cohort_source=result['path'],physical_cohort_sha256=result['sha256'],physical_cohort_seconds=raw['seconds'],
            logical_zero_seconds_are_projection_only=True)))
    return result,projections


def run(engine,task,pool):
    began=time.monotonic();worker=socket.gethostname()+'_'+str(os.getpid());active=[]
    for entry in task['entries']:
        base=ROOT/entry['stage'];t=entry['task']
        if (base/'receipts'/(t['id']+'.json')).exists():continue
        claim=base/'claims'/t['id'];claim.parent.mkdir(parents=True,exist_ok=True)
        try:claim.mkdir()
        except FileExistsError:continue
        atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,pid=os.getpid(),hostname=socket.gethostname(),policy_cohort=task['id']));active.append(entry)
    if not active:return dict(status='ALREADY_ACCOUNTED_FOR',original_tasks=0)
    try:
        for entry in active:
            existing=ROOT/entry['stage']/'results'/(entry['task']['id']+'.json')
            assert not existing.exists(),('Unreceipted original result must be preserved',str(existing.relative_to(ROOT)))
        if len(active)==1:
            entry=active[0];source=ROOT/entry['handler'];key=entry['handler_sha256'];assert sha(source)==key
            if key not in MODULES:
                spec=importlib.util.spec_from_file_location('cohort_single_'+key,source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);MODULES[key]=module
            result=MODULES[key].run(engine,entry['task'],pool);engine.verify_engine();elapsed=time.monotonic()-began
            atomic(ROOT/entry['stage']/'receipts'/(entry['task']['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=entry['task'],worker=worker,seconds=elapsed,result=result,policy_cohort=task['id'],compute_mode='unchanged_single_original_task',scientific_handler={k:entry[k] for k in ['handler','handler_sha256']}|dict(kind='custom')))
            return dict(original_tasks=1,physical_result=result,seconds=elapsed,single_original_fallback=True)
        result,projections=execute(engine,active,pool,task['stage'],task['id']+'_physical');saved=[]
        for item in projections:
            entry=item['entry'];t=entry['task'];base=ROOT/entry['stage'];path=base/'results'/(t['id']+'.json');assert not path.exists();atomic(path,item['raw']);hashed=sha(path)
            value=dict(path=str(path.relative_to(ROOT)),sha256=hashed,records=len(item['raw']['records']),seconds=0.,physical_cohort_source=result['path'],physical_cohort_seconds=item['raw']['physical_cohort_seconds'],projection_time_not_model_time=True)
            atomic(base/'receipts'/(t['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=t,worker=worker,seconds=0.,result=value,policy_cohort=task['id'],
                scientific_handler={k:entry[k] for k in ['handler','handler_sha256']}|dict(kind='custom'),compute_mode='exact_shared_scene_policy_projection'))
            saved.append(dict(stage=entry['stage'],id=t['id'],sha256=hashed))
        engine.verify_engine();return dict(original_tasks=len(saved),physical_result=result,projections=saved,seconds=time.monotonic()-began,unchanged_original_evaluator=True)
    except BaseException as error:
        import traceback
        for entry in active:
            t=entry['task'];failure=dict(status='FAILED',time=stamp(),task=t,worker=worker,error=repr(error),traceback=traceback.format_exc(),policy_cohort=task['id'])
            atomic(ROOT/entry['stage']/'failures'/(t['id']+'.json'),failure)
        raise
