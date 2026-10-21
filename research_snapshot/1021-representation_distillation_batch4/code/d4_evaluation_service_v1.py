"""Cooperative full evaluation on each group's retained Base model services."""
from d4_common_v2 import *
import traceback
from d4_evaluate_student_v1 import run as evaluate,release_private_student
from functools import lru_cache

CURSORS={}
SETUP=False


def run_one(engine,node,worker,pool):
    global SETUP
    import numpy as np
    assigned=next((n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['job']==node['job']),None)
    if assigned is None:return False
    registry=ROOT/'runs/EVALUATION_QUEUE.json'
    if not registry.exists():return False
    key=node['name']+'_device%02d_pid%d'%(worker['device'],worker['pid'])
    for setting in sorted(read(registry)['stages'],key=lambda v:(v['priority'],v['id'])):
        if setting['group']!=assigned['group']:continue
        stage=ROOT/setting['stage']
        if (stage/'AGENT_ACCEPTANCE.json').exists():continue
        if any(not (ROOT/p).exists() for p in setting.get('requires',[])):continue
        if next((stage/'failures').glob('*.json'),None) is not None:return False
        descriptor=read(ROOT/'runs/EVALUATION_EXECUTOR.json')
        assert sha(ROOT/'code/d4_evaluate_student_v1.py')==descriptor['evaluator_sha256']
        if not SETUP:
            setup('evaluation_resident/'+key,threads=1);compatibility();SETUP=True
        spec=document(stage/'SPECIFICATION.json',setting['specification_sha256'])
        if setting['kind']=='engineering':
            folder=stage/'workers'/key
            if (folder/'PASS.json').exists():continue
            claim=folder/'CLAIM';claim.parent.mkdir(parents=True,exist_ok=True)
            try:claim.mkdir()
            except FileExistsError:continue
            try:
                results=[]
                for valid_only in [False,True]:
                    scope='valid_format' if valid_only else 'full_context'
                    task=dict(spec['task_template'],id=key+'_'+scope,indices=spec['indices'],output_stage=str((folder/scope).relative_to(ROOT)),
                        engineering=True,valid_only_engineering=valid_only)
                    result=evaluate(engine,task,pool);golden={}
                    oldstage=ROOT/spec['golden_development_stage']
                    for p in oldstage.glob('rank*.json'):
                        for old in read(p)['cases']:golden[old['global_index']]=old
                    for case in read(result['path'])['cases']:
                        record=read(ROOT/case['path']);old=golden[case['global_index']]
                        with np.load(ROOT/record['arrays']['path'],allow_pickle=False) as z:
                            assert np.array_equal(z['student_trajectories'][:5],np.asarray(old['trajectories'],dtype=np.float32))
                            assert np.array_equal(z['student_quality'][:5],np.asarray(old['quality'],dtype=np.float64))
                    results.append(result)
                atomic(folder/'PASS.json',dict(status='PASS_RETAINED_STUDENT_EVALUATION_LANE_EXACT',time=stamp(),worker=worker,
                    results=results,old_five_scores_and_trajectories_exact=True,new_five_Base_replay_check_exact=True,actual_test_used=False))
                markers=[read(p) for p in (stage/'workers').glob('*/PASS.json')]
                counts={int(d):0 for d in spec['devices']}
                for m in markers:counts[int(m['worker']['device'])]+=1
                if counts and all(v==spec['lanes_per_device'] for v in counts.values()):
                    atomic(stage/'ALL_LANES_READY.json',dict(status='ALL_EVALUATION_LANES_READY_REQUIRES_AGENT_REVIEW',time=stamp(),group=setting['group'],devices=len(counts),lanes=len(markers)))
            except BaseException as error:
                atomic(stage/'failures'/(key+'.json'),dict(status='FAILED',time=stamp(),worker=worker,error=repr(error),traceback=traceback.format_exc()));raise
            return True
        assert setting['kind']=='formal'
        cursor=CURSORS.get(setting['id'],0)
        while cursor<spec['case_count']:
            offset=cursor;cursor+=spec['chunk_size'];CURSORS[setting['id']]=cursor;ident=setting['id']+'_%06d'%offset
            if (stage/'receipts'/(ident+'.json')).exists():continue
            claim=stage/'claims'/ident;claim.parent.mkdir(parents=True,exist_ok=True)
            try:claim.mkdir()
            except FileExistsError:continue
            indices=document(spec['indices_path'],spec['indices_sha256'])[offset:cursor] if 'indices_path' in spec else list(range(offset,min(cursor,spec['case_count'])))
            task=dict(spec['task_template'],id=ident,indices=indices,output_stage=str(stage.relative_to(ROOT)))
            atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,task=task,specification_sha256=setting['specification_sha256']))
            live=ROOT/'runs/evaluation_workers'/key
            atomic(live.with_suffix('.json'),dict(status='COMPUTING',time=stamp(),worker=worker,task=ident,stage=setting['stage']))
            try:
                result=evaluate(engine,task,pool)
                atomic(stage/'receipts'/(ident+'.json'),dict(status='COMPLETE',time=stamp(),worker=worker,task=task,result=result,
                    specification_sha256=setting['specification_sha256']))
            except BaseException as error:
                atomic(stage/'failures'/(ident+'.json'),dict(status='FAILED',time=stamp(),worker=worker,task=task,error=repr(error),traceback=traceback.format_exc()));raise
            return True
    return False


@lru_cache(maxsize=32)
def document(path,expected):
    assert sha(path)==expected
    return read(path)
