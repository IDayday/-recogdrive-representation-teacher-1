"""Training-only strength/abstention selection, then whole-system held sessions."""
from r2_common import *
from r2_resume_support import register_once,enqueue
from r2_coarse_producer import balanced
from collections import defaultdict


def main():
    setup('additional_joint_policy_cv_producer')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);explore=np.array([r['subset']=='exploration' for r in rows])
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows]);selected=set();handled=set();panels={}
    stage=ROOT/'runs/additional_joint_policy_cv_v1';handler='code/r2_additional_joint_eval.py'
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[])
    if not (stage/'producer.json').exists():atomic(stage/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='additional_joint_policy_whole_system_session_CV',path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=22.4))
    queue=read(stage/'tasks.json');known={t['id'] for t in queue}
    while True:
        for response_path in (ROOT/'analysis/responses/additional_joint_quick_v1').glob('*.json'):
            response=read(response_path);point=read(ROOT/response['point']);ident=point['id']
            if ident in selected:continue
            model=read(ROOT/point['training_path']);held=model['heldout_fold'];role=model['role'];train=explore&((folds!=held) if held>=0 else True)
            populations=[np.sum(train&(quality<.7)),np.sum(train&(quality>.9)),np.sum(train&(quality>=.7)&(quality<=.9))]
            with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);s=np.array(z['scores']);ids=list(z['arm_ids'])
            assert np.all(train[ii]);classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));counts=np.bincount(classes,minlength=3)
            weights=np.asarray([populations[c]/counts[c] for c in classes]);weights/=weights.sum();candidates=[]
            for j,arm in enumerate(ids):
                a=s[:,j];b=s[:,0];rates=[float(np.sum(weights[:,None]*((a[:,:,c]<1).astype(float)-(b[:,:,c]<1).astype(float)))/a.shape[1]) for c in [1,2]]
                rates.append(float(np.sum(weights[:,None]*((a[:,:,0]==0).astype(float)-(b[:,:,0]==0).astype(float)))/a.shape[1]))
                gain=float(np.sum(weights[:,None]*(a[:,:,0]-b[:,:,0]))/a.shape[1]);safe=all(v<=1e-12 for v in rates)
                candidates.append(dict(arm=arm,pdms_gain=gain,collision_delta=rates[0],offroad_delta=rates[1],zero_delta=rates[2],safe=safe))
            eligible=[c for c in candidates if c['safe']] if role=='safety' else candidates;assert eligible
            choice=max(eligible,key=lambda c:(c['pdms_gain'],c['arm']=='baseline'))
            if choice['arm']=='baseline':configuration=dict(point['policies'][0],id=ident+'_selected',force_Base=True)
            else:configuration=dict(next(p for p in point['policies'] if p['id']==choice['arm']),id=ident+'_selected')
            path=ROOT/'additional_joint_policies'/ident/'POLICY.json'
            if not path.exists():atomic(path,dict(status='TRAINING_SELECTED_NOT_HELDOUT_VERIFIED',time=stamp(),system=model['system'],heldout_fold=held,kind=model['kind'],tier=model['tier'],role=role,
                nominal_K=model['nominal_K'],active_K=model['active_K'],configuration=configuration,candidates=candidates,chosen_metrics=choice,source_response=str(response_path.relative_to(ROOT)),
                safety_scope='Training estimate only; held-session net safety is separately measured.',validation_fitted=False,test_accessed=False))
            selected.add(ident)
        groups=defaultdict(dict)
        for p in (ROOT/'additional_joint_policies').glob('*/POLICY.json'):
            d=read(p);groups[(d['heldout_fold'],d['system'],d['kind'])][(d['role'],d['tier'])]=d
        changed=False
        for key,entries in groups.items():
            held,system,kind=key
            if held<0 or key in handled or len(entries)!=6:continue
            if held not in panels:
                mask=explore&(folds==held);salt=dict(joint_outer_panel=20261018,held=held)
                parts=dict(failure=np.flatnonzero(mask&(quality<.7)).tolist(),high=balanced(np.flatnonzero(mask&(quality>.9)),rows,512,salt),intermediate=balanced(np.flatnonzero(mask&(quality>=.7)&(quality<=.9)),rows,256,salt))
                panels[held]=(sum(parts.values(),[]),parts)
            panel,partitions=panels[held];ident='additional_joint_cv_'+digest(dict(held=held,system=system,kind=kind))[:24];path=stage/'points'/(ident+'.json')
            if not path.exists():atomic(path,dict(id=ident,mode='heldout',heldout_fold=held,system=system,kind=kind,policies=[dict(d['configuration'],id=role+'_'+tier) for (role,tier),d in sorted(entries.items())],panel=panel,panel_partitions=partitions,seeds=[0,1,2],full_system_outer_cv=True,validation_accessed=False,test_accessed=False))
            for start in range(0,len(panel),4):enqueue(queue,known,dict(id=ident+'_%04d'%start,point=str(path.relative_to(ROOT)),start=start,end=min(start+4,len(panel)),stage=str(stage.relative_to(ROOT))))
            handled.add(key);changed=True
        if changed:atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=False,tasks=len(queue),systems=len(handled),time=stamp()))
        atomic(ROOT/'analysis/additional_joint_policy_selection/PRODUCER.json',dict(time=stamp(),training_selected=len(selected),held_systems_queued=len(handled)))
        time.sleep(60)


if __name__=='__main__':main()
