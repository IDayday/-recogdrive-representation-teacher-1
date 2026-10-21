"""Prepare a frozen trajectory-learning grid and stream checkpoint rescoring.

Calibration is exploratory engineering. Its full grid is preserved for CV; no
held-out claim follows from selecting its best training outcome.
"""
from r2_common import *
from r2_coarse_producer import balanced


def register(stage):
    with (ROOT/'config/gpu_stages.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        path=ROOT/'config/GPU_STAGES.json';d=read(path)
        assert stage['name'] not in {s['name'] for s in d['stages']}
        d['stages'].append(stage);d['time']=stamp();atomic(path,d)


def main():
    setup('learner_calibration_producer')
    import numpy as np
    pre=ROOT/'analysis/expert_spaces/space_learned_calibration_pre.json'
    while not pre.exists():time.sleep(15)
    metadata=[read(pre),read(ROOT/'analysis/expert_spaces/space_pilot_interface_post.json')]
    train=ROOT/'runs/learned_calibration_v1';evaluation=ROOT/'runs/learned_calibration_eval_v1'
    assert not (train/'producer.json').exists()
    tasks=[]
    for d in metadata:
        assert d['status']=='PASS'
        for space in ['success','residual','full']:
            choices=[f for f in d['fits'] if f['config']['kind']==('basis_residual' if space=='residual' else 'success_pca')]
            fit=min(choices,key=lambda f:f['r'])
            for rank in [8,32]:
                for cap in [.02,.1]:
                    spec=dict(responsibility_meta='analysis/initial_groups/all/representation_K3_seed0.json',
                         expert=0,block=fit['block'],group=fit['group'],fit_path=fit['path'],fit_sha256=fit['sha256'],
                         fit_seed=2026101801,heldout_fold=-1,rank=rank,cap=cap,steps=256,checkpoints=[64,128,256],
                         learning_rate=.003,edit_penalty=.0001,retention_weight=2.,space_control='full' if space=='full' else 'quality')
                    tasks.append(dict(id='learncal_'+digest(spec)[:20],handler='code/r2_learned_expert.py',
                                      handler_sha256=sha(ROOT/'code/r2_learned_expert.py'),**spec))
    atomic(train/'tasks.json',tasks);atomic(train/'producer.json',dict(complete=True,tasks=len(tasks),time=stamp()))
    atomic(train/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),tasks=len(tasks),K=3,expert=0,seed_replicate=0,
           sites=['interface_pre','interface_post'],spaces=['success','residual','full'],ranks=[8,32],caps=[.02,.1],
           checkpoints=[64,128,256],purpose='Engineering calibration; grid retained for proper CV',
           fit_on_exploration=True,validation_accessed=False,test_accessed=False))
    atomic(evaluation/'tasks.json',[]);atomic(evaluation/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register(dict(name='trajectory_trained_expert_calibration',path=str(train.relative_to(ROOT)),
                  handler='code/r2_learned_expert.py',handler_sha256=sha(ROOT/'code/r2_learned_expert.py'),kind='custom',priority=20))
    register(dict(name='trajectory_trained_expert_calibration_rescoring',path=str(evaluation.relative_to(ROOT)),
                  handler='code/r2_learned_eval.py',handler_sha256=sha(ROOT/'code/r2_learned_eval.py'),kind='custom',priority=19))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    explore=np.array([r['subset']=='exploration' for r in rows]);salt=dict(learned_calibration=20261018)
    panel=balanced(np.flatnonzero(explore&(q<.7)),rows,32,salt)+balanced(np.flatnonzero(explore&(q>.9)),rows,24,salt)+balanced(np.flatnonzero(explore&(q>=.7)&(q<=.9)),rows,8,salt)
    handled=set();queue=[]
    while len(handled)<len(tasks):
        changed=False
        for task in tasks:
            if task['id'] in handled:continue
            ready=ROOT/'learned_experts'/task['id']/'TRAINING.json'
            if not ready.exists():continue
            d=read(ready);arms=[]
            assert len(d['checkpoints'])==3
            for checkpoint in d['checkpoints']:
                for strength in [0.,.25,.5,1.]:
                    spec=dict(training_task=task,checkpoint=checkpoint,strength=strength)
                    arms.append(dict(id='learned_'+digest(spec)[:20],**spec))
            point=evaluation/'points'/(task['id']+'.json');atomic(point,dict(arms=arms,panel=panel,seeds=[0,1,2],training_only=True))
            for start in range(0,len(panel),4):
                queue.append(dict(id=task['id']+'_%03d'%start,point=str(point.relative_to(ROOT)),start=start,
                                  end=min(start+4,len(panel)),stage=str(evaluation.relative_to(ROOT))))
            handled.add(task['id']);changed=True
        if changed:
            atomic(evaluation/'tasks.json',queue)
            atomic(evaluation/'producer.json',dict(complete=False,tasks=len(queue),trained=len(handled),time=stamp()))
        if len(handled)<len(tasks):time.sleep(30)
    atomic(evaluation/'producer.json',dict(complete=True,tasks=len(queue),trained=len(handled),time=stamp()))
    print(json.dumps(dict(status='PRODUCED',trained=len(handled),evaluation_tasks=len(queue))),flush=True)


if __name__=='__main__':main()
