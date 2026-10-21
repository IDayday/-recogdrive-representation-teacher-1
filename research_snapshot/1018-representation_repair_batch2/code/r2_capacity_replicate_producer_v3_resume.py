"""Stream matched capacity controls across outer folds and whole-fit seeds.

Only already verified mathematical handlers execute training and inference.
The completed fit0/fold0 pilot is reused by an explicit column projection.
"""
from r2_common import *
from r2_resume_support import register_once,enqueue,append_once
from r2_coarse_producer import balanced
from collections import defaultdict


def stage(name,handler):
    base=ROOT/'runs'/name
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[]);atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name=name,path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=24.,enabled=False))
    return base


def chunks(base,point,size):
    d=read(point)
    return [dict(id=d['id']+'_%04d'%start,stage=str(base.relative_to(ROOT)),point=str(point.relative_to(ROOT)),start=start,end=min(start+size,len(d['panel']))) for start in range(0,len(d['panel']),size)]


def main():
    setup('capacity_replicate_producer')
    import numpy as np
    protocolpath='config/CAPACITY_REPLICATION_PROTOCOL_V1.json';protocol=read(ROOT/protocolpath);frozen=sha(ROOT/protocolpath)
    training=stage('capacity_replication_training_v1','code/r2_expert_capacity_training.py');quick=stage('capacity_replication_quick_v1','code/r2_expert_capacity_eval_cached.py')
    feedbacks=[stage('capacity_replication_S0_v1','code/r2_library_rollouts.py'),stage('capacity_replication_noise_v1','code/r2_library_rollouts.py')]
    original=read(ROOT/'runs/behavior_experts_v1/tasks.json');parents=[t for t in original if t['system'] in [f'correction_K3_seed{i}' for i in range(3)]];assert len(parents)==108
    groups=defaultdict(list);training_tasks=[];descriptors={}
    for parent in parents:
        held=parent['heldout_fold'];fit_index=int(parent['system'][-1]);groups[(fit_index,held)].append(parent)
        originalpath=ROOT/'learned_experts'/parent['id']/'TRAINING.json';assert originalpath.exists()
        model=read(originalpath);assert model.get('canonical_configuration',model['task'])==parent
        descriptors[(parent['id'],32)]=dict(path=str(originalpath.relative_to(ROOT)),training_task=parent)
        if fit_index==0 and held==0:continue
        spec=dict(parent,rank=128,steps=parent['steps']*4,checkpoints=[parent['steps'],parent['steps']*4],capacity_replication=True,parent_task=parent['id'],protocol=protocolpath,protocol_sha256=frozen)
        spec.pop('id');task=dict(id='capacityrep_train_'+digest(spec)[:24],**spec);training_tasks.append(task)
        descriptors[(parent['id'],128)]=dict(path='expert_capacity_controls/models/'+task['id']+'/TRAINING.json',training_task=task)
    assert len(groups)==18 and len(training_tasks)==102
    training_tasks.sort(key=lambda t:(t['heldout_fold']<0,t['fit_seed'],t['heldout_fold'],t['expert'],t['block']))
    old=read(training/'tasks.json');assert not old or old==training_tasks
    if not old:atomic(training/'tasks.json',training_tasks);atomic(training/'producer.json',dict(complete=True,time=stamp(),tasks=102))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);explore=np.array([r['subset']=='exploration' for r in rows])
    quickqueue=read(quick/'tasks.json');qknown={t['id'] for t in quickqueue};feedbackqueues={b:read(b/'tasks.json') for b in feedbacks};fknown={b:{t['id'] for t in v} for b,v in feedbackqueues.items()};prepared=set();reduced=set();bankqueued=set();feedbackprepared=set();aliased=set();panelcache={}
    while True:
        assert sha(ROOT/protocolpath)==frozen;work=[];quickchanged=False;feedbackchanged=False
        for key,models in sorted(groups.items(),key=lambda p:(p[0][0],p[0][1]<0,p[0][1])):
            fit_index,held=key
            if key==(0,0):continue
            train=explore&((fold!=held) if held>=0 else True)
            if held not in panelcache:
                salt=dict(behavior_expert_panel=20261018,held=held);quickparts={name:balanced(np.flatnonzero(train&cond),rows,count,salt) for name,cond,count in [('failure',q<.7,32),('high',q>.9,24),('intermediate',(q>=.7)&(q<=.9),8)]}
                salt=dict(expert_library_panel=20261018,held=held);failure=np.flatnonzero(train&(q<.7)).tolist();high=balanced(np.flatnonzero(train&(q>.9)),rows,256,salt);middle=balanced(np.flatnonzero(train&(q>=.7)&(q<=.9)),rows,128,salt)
                panelcache[held]=(quickparts,[dict(failure=failure,high=high,intermediate=middle),dict(failure=balanced(failure,rows,256,salt),high=high[:128],intermediate=middle[:64])])
            quickparts,fullparts=panelcache[held];responses=[]
            for parent in models:
                for rank in [32,128]:
                    descriptor=descriptors[(parent['id'],rank)];mp=ROOT/descriptor['path'];t=descriptor['training_task'];ident='capacityrep_quick_'+digest(dict(parent=parent['id'],rank=rank))[:24];response='analysis/responses/'+quick.name+'/'+ident+'.json';responses.append(response)
                    if not mp.exists():continue
                    if ident not in prepared:
                        m=read(mp);assert m.get('canonical_configuration',m['task'])==t;arms=[]
                        for factor in ([1] if rank==32 else [1,4]):
                            ck=next(c for c in m['checkpoints'] if c['step']==parent['steps']*factor);assert sha(ROOT/ck['path'])==ck['sha256']
                            for strength in [.25,.5,1.]:
                                spec=dict(training_task=t,checkpoint=ck,strength=strength,budget_factor=factor);arms.append(dict(id='capacityrep_arm_'+digest(spec)[:24],kind='learned',slot=parent['expert'],**spec))
                        point=quick/'points'/(ident+'.json')
                        if not point.exists():atomic(point,dict(id=ident,task=t,arms=arms,panel=sum(quickparts.values(),[]),panel_partitions=quickparts,seeds=[0,1,2],training_only=True,mode='training'))
                        for item in chunks(quick,point,4):enqueue(quickqueue,qknown,item)
                        prepared.add(ident);quickchanged=True
                    point=quick/'points'/(ident+'.json');tasks=chunks(quick,point,4)
                    if ident not in reduced and all((quick/'receipts'/(t['id']+'.json')).exists() for t in tasks):
                        work.append(dict(id='outcome_capacityrep_reduce_'+ident,handler='code/r2_point_response.py',handler_sha256=sha(ROOT/'code/r2_point_response.py'),stage=str(quick.relative_to(ROOT)),point=str(point.relative_to(ROOT)),chunks=[t['id'] for t in tasks]));reduced.add(ident)
            bankid='outcome_capacityrep_select_'+digest(dict(fit=fit_index,held=held))[:24]
            if key not in bankqueued and all((ROOT/p).exists() for p in responses):
                work.append(dict(id=bankid,handler='code/r2_capacity_replicate_select.py',handler_sha256=sha(ROOT/'code/r2_capacity_replicate_select.py'),protocol=protocolpath,heldout_fold=held,fit_index=fit_index,parent_system=models[0]['system'],responsibility_meta=models[0]['responsibility_meta'],responses=responses));bankqueued.add(key)
            bankpath=ROOT/'analysis/capacity_replication_banks'/(bankid+'.json')
            if not bankpath.exists():continue
            selections=read(bankpath)['selections'];union={}
            for path in selections:
                s=read(ROOT/path)
                for arm in s['arms']:union[arm['id']]=arm
            unionid='capacityrep_feedback_'+digest(dict(fit=fit_index,held=held))[:24]
            for j,base in enumerate(feedbacks):
                point=base/'points'/(unionid+'.json')
                if not point.exists():atomic(point,dict(id=unionid,system='capacity_replication_physical_union_only',K=3,heldout_fold=held,arms=list(union.values()),panel=sum(fullparts[j].values(),[]),panel_partitions=fullparts[j],seeds=[0] if j==0 else [1,2],training_only=True,actual_outcome_cv=False))
                marker=(key,j);tasks=chunks(base,point,8)
                if marker not in feedbackprepared:
                    for item in tasks:enqueue(feedbackqueues[base],fknown[base],item)
                    feedbackprepared.add(marker);feedbackchanged=True
                if marker not in reduced and all((base/'receipts'/(t['id']+'.json')).exists() for t in tasks):
                    work.append(dict(id='outcome_capacityrep_feedback_'+str(j)+'_'+unionid,handler='code/r2_point_response_v2.py',handler_sha256=sha(ROOT/'code/r2_point_response_v2.py'),stage=str(base.relative_to(ROOT)),point=str(point.relative_to(ROOT)),chunks=[t['id'] for t in tasks]));reduced.add(marker)
                responsepath=ROOT/'analysis/responses'/base.name/(unionid+'.json')
                if responsepath.exists() and marker not in aliased:
                    response=read(responsepath)
                    for selectionpath in selections:
                        selection=read(ROOT/selectionpath);alias=Path(selectionpath).name;aliaspoint=base/'points'/alias;destination=ROOT/'analysis/responses'/base.name/alias
                        expected_point=dict(read(point),id=Path(alias).stem,system=selection['system'],own_K_selection=selectionpath,physical_union_source=str(point.relative_to(ROOT)))
                        expected_response=dict(response,point=str(aliaspoint.relative_to(ROOT)),shared_exact_physical_matrix=True,physical_response=str(responsepath.relative_to(ROOT)),physical_response_sha256=sha(responsepath),own_K_selection=selectionpath,union_not_deployable_policy=True)
                        for existing_path,expected_value in [(aliaspoint,expected_point),(destination,expected_response)]:
                            if existing_path.exists():assert digest(read(existing_path))==digest(expected_value),str(existing_path)
                            else:atomic(existing_path,expected_value)
                    aliased.add(marker)
        if work:append_once('cpu',work)
        if quickchanged:atomic(quick/'tasks.json',quickqueue);atomic(quick/'producer.json',dict(time=stamp(),tasks=len(quickqueue),complete=len(prepared)==204,models_ready=len(prepared)))
        if feedbackchanged:
            for base,queue in feedbackqueues.items():atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(time=stamp(),tasks=len(queue),complete=False))
        atomic(ROOT/'analysis/capacity_replication/PRODUCER.json',dict(time=stamp(),new_expert_models=102,new_expert_models_ready=sum((ROOT/d['path']).exists() for (parent,rank),d in descriptors.items() if rank==128),quick_points_ready=len(prepared),quick_required=204,banks_queued=len(bankqueued),group_feedback_ready=len(aliased),group_feedback_required=34,fold0_fit0_reuse='Separate exact completed-pilot projection, no rerun',no_natural_confirmation_or_test=True))
        time.sleep(30)


if __name__=='__main__':main()
