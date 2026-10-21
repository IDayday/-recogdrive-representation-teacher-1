"""Bounded18-model capacity pilot; original experiments remain untouched."""
from r2_common import *
from r2_resume_support import register_once,enqueue,append_once
from r2_coarse_producer import balanced


def stage(name,handler,priority,enabled=False):
    folder=ROOT/'runs'/name
    if not (folder/'tasks.json').exists():atomic(folder/'tasks.json',[]);atomic(folder/'producer.json',dict(time=stamp(),complete=False,tasks=0))
    register_once(dict(name=name,path=str(folder.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=priority,enabled=enabled));return folder


def main():
    setup('expert_capacity_producer')
    import numpy as np
    protocol_path='config/EXPERT_CAPACITY_CONTROL_PROTOCOL_V1.json';protocol=read(ROOT/protocol_path);protocol_hash=sha(ROOT/protocol_path);workflow='code/r2_expert_capacity_workflow.py';workflow_hash=sha(ROOT/workflow)
    engineering=stage('expert_capacity_engineering_v1',workflow,8,True);eng=dict(id='expert_capacity_engineering_v1',protocol=protocol_path,protocol_sha256=protocol_hash)
    if not read(engineering/'tasks.json'):atomic(engineering/'tasks.json',[eng]);atomic(engineering/'producer.json',dict(time=stamp(),complete=True,tasks=1))
    while not (ROOT/'provenance/EXPERT_CAPACITY_CONTROL_ENGINEERING_PASS.json').exists():time.sleep(30)
    training=stage('expert_capacity_training_v1','code/r2_expert_capacity_training.py',24.0);quick=stage('expert_capacity_quick_v1','code/r2_expert_capacity_eval_cached.py',23.8);heldstage=stage('expert_capacity_held_v1','code/r2_expert_capacity_eval_cached.py',22.2)
    original=read(ROOT/'runs/behavior_experts_v1/tasks.json');tasks=[]
    for parent in original:
        if parent['system']!=protocol['system'] or parent['heldout_fold']!=protocol['outer_fold']:continue
        for rank in protocol['ranks']:
            base_steps=parent['steps'];spec=dict(parent,rank=rank,steps=base_steps*8,checkpoints=sorted(set(parent['checkpoints']+[base_steps*4,base_steps*8])),capacity_control=True,parent_task=parent['id'],protocol=protocol_path,protocol_sha256=protocol_hash)
            spec.pop('id');tasks.append(dict(id='capacity_train_'+digest(spec)[:24],**spec))
    assert len(tasks)==18
    if not read(training/'tasks.json'):atomic(training/'tasks.json',tasks);atomic(training/'producer.json',dict(time=stamp(),complete=True,tasks=len(tasks)))
    else:assert read(training/'tasks.json')==tasks
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);mask=np.array([r['subset']=='exploration' for r in rows])&(fold!=0);salt=dict(behavior_expert_panel=20261018,held=0)
    parts=dict(failure=balanced(np.flatnonzero(mask&(q<.7)),rows,32,salt),high=balanced(np.flatnonzero(mask&(q>.9)),rows,24,salt),intermediate=balanced(np.flatnonzero(mask&(q>=.7)&(q<=.9)),rows,8,salt));panel=sum(parts.values(),[])
    qq=read(quick/'tasks.json');known={t['id'] for t in qq};hq=read(heldstage/'tasks.json');hk={t['id'] for t in hq};prepared=set();reduced=set();selection_queued=False;held_prepared=False;held_reduced=False;analysis_queued=False
    while True:
        assert sha(ROOT/protocol_path)==protocol_hash;work=[];changed=False
        for t in tasks:
            modelpath=ROOT/'expert_capacity_controls/models'/t['id']/'TRAINING.json'
            if not modelpath.exists():continue
            if t['id'] not in prepared:
                model=read(modelpath);assert model['task']==t;arms=[];base_steps=t['steps']//8
                for factor in protocol['budget_factors']:
                    ck=next(c for c in model['checkpoints'] if c['step']==base_steps*factor)
                    for strength in protocol['strengths']:
                        spec=dict(training_task=t,checkpoint=ck,strength=strength,budget_factor=factor);arms.append(dict(id='capacity_arm_'+digest(spec)[:24],kind='learned',slot=t['expert'],**spec))
                point=quick/'points'/(t['id']+'.json')
                if not point.exists():atomic(point,dict(id=t['id'],task=t,arms=arms,panel=panel,panel_partitions=parts,seeds=[0,1,2],training_only=True,mode='training'))
                for j in range(0,len(panel),4):enqueue(qq,known,dict(id=t['id']+'_%03d'%j,stage=str(quick.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=j,end=min(j+4,len(panel))))
                prepared.add(t['id']);changed=True
            chunks=[t['id']+'_%03d'%j for j in range(0,len(panel),4)]
            if t['id'] not in reduced and all((quick/'receipts'/(c+'.json')).exists() for c in chunks):
                spec=dict(id='outcome_capacity_quick_'+t['id'],handler='code/r2_point_response.py',handler_sha256=sha(ROOT/'code/r2_point_response.py'),stage=str(quick.relative_to(ROOT)),point=str((quick/'points'/(t['id']+'.json')).relative_to(ROOT)),chunks=chunks);work.append(spec);reduced.add(t['id'])
        responses=['analysis/responses/'+quick.name+'/'+t['id']+'.json' for t in tasks]
        if not selection_queued and all((ROOT/p).exists() for p in responses):
            work.append(dict(id='outcome_capacity_bank_select_v1',handler=workflow,handler_sha256=workflow_hash,mode='select',protocol=protocol_path,responsibility_meta=tasks[0]['responsibility_meta'],responses=responses));selection_queued=True
        bankfile=ROOT/'expert_capacity_controls/banks/COMPLETE.json'
        if bankfile.exists() and not held_prepared:
            banks=read(bankfile);cache_path=next(p for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json') if read(p)['system']==protocol['system'] and read(p)['heldout_fold']==0);cache=read(cache_path)
            with np.load(ROOT/cache['matrix']) as z:held_panel=np.array(z['global_indices']).tolist()
            point=heldstage/'points/capacity_held_union.json'
            if not point.exists():atomic(point,dict(id='capacity_held_union',mode='heldout',heldout_fold=0,panel=held_panel,seeds=[0,1,2],arms=banks['parts'],banks=banks['banks'],training_only=False,diagnostic_only=True,each_policy_has_own3_parts=True,source_original_case_panel=str(cache_path.relative_to(ROOT))))
            for j in range(0,len(held_panel),2):enqueue(hq,hk,dict(id='capacity_held_union_%04d'%j,stage=str(heldstage.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=j,end=min(j+2,len(held_panel))))
            atomic(heldstage/'tasks.json',hq);atomic(heldstage/'producer.json',dict(time=stamp(),complete=True,tasks=len(hq)));held_prepared=True
        if held_prepared and not held_reduced and all((heldstage/'receipts'/(t['id']+'.json')).exists() for t in hq):
            work.append(dict(id='outcome_capacity_held_reduce_v1',handler='code/r2_point_response.py',handler_sha256=sha(ROOT/'code/r2_point_response.py'),stage=str(heldstage.relative_to(ROOT)),point=str((heldstage/'points/capacity_held_union.json').relative_to(ROOT)),chunks=[t['id'] for t in hq]));held_reduced=True
        response=ROOT/'analysis/responses'/heldstage.name/'capacity_held_union.json'
        if response.exists() and not analysis_queued:work.append(dict(id='outcome_capacity_analysis_v1',handler=workflow,handler_sha256=workflow_hash,mode='analyze',response=str(response.relative_to(ROOT))));analysis_queued=True
        if work:append_once('cpu',work)
        if changed:atomic(quick/'tasks.json',qq);atomic(quick/'producer.json',dict(time=stamp(),complete=len(prepared)==18,tasks=len(qq),models_ready=len(prepared)))
        atomic(ROOT/'analysis/expert_capacity_control/PRODUCER.json',dict(time=stamp(),formal_models=len(tasks),models_ready=len(prepared),quick_matrices_ready=sum((ROOT/p).exists() for p in responses),held_prepared=held_prepared,held_reduced=held_reduced,analysis_queued=analysis_queued,not_deployable_or_final_confirmation=True))
        if (ROOT/'analysis/expert_capacity_control/SUMMARY.json').exists():return
        time.sleep(30)


if __name__=='__main__':main()
