"""Broad actual-score calibration of conditional, outcome-derived delta spaces."""
from r2_common import *
from r2_resume_support import append_once,register_once
from r2_coarse_producer import balanced


def main():
    setup('delta_calibration_producer')
    import numpy as np
    required=ROOT/'runs/delta_eval_smoke_v2/receipts/delta_eval_smoke.json'
    while not required.exists():time.sleep(15)
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')};tasks=[]
    for block in ['interface_pre','interface_post']:
        dimension=cells[block+'__valid_mean']['shape'][1]
        for cap in [.02,.1]:
            spec=dict(block=block,cap=cap,responsibility_meta='analysis/initial_groups/all/representation_K3_seed0.json',
                 expert=0,heldout_fold=-1,fit_seed=2026101801,input_ranks=sorted({r for r in [32,128,256,768,dimension] if r<=dimension}),
                 output_ranks=sorted({r for r in [8,32,128,256,512,1024,dimension] if r<=dimension}),
                 ridge=[.01,.1,1.,10.],retention_weight=2.,safety_targets=False)
            tasks.append(dict(id='outcome_delta_cal_'+digest(spec)[:22],handler='code/r2_delta_regression_v2.py',
                              handler_sha256=sha(ROOT/'code/r2_delta_regression_v2.py'),**spec))
    protocol=ROOT/'config/DELTA_CALIBRATION_PROTOCOL.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),tasks=tasks,
         selection='Evaluate all fitted settings by actual outcomes; energy and regression error are descriptors only.',
         training_only=True,validation_fitted=False,test_accessed=False))
    append_once('cpu',tasks)
    base=ROOT/'runs/delta_calibration_eval_v1'
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[])
    if not (base/'producer.json').exists():atomic(base/'producer.json',dict(complete=False,tasks=0,time=stamp()))
    register_once(dict(name='delta_causal_space_actual_calibration',path=str(base.relative_to(ROOT)),handler='code/r2_delta_eval_v2.py',
                       handler_sha256=sha(ROOT/'code/r2_delta_eval_v2.py'),kind='custom',priority=21))
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);explore=np.array([r['subset']=='exploration' for r in rows]);salt=dict(delta_calibration=20261018)
    failure=balanced(np.flatnonzero(explore&(q<.7)),rows,16,salt);high=balanced(np.flatnonzero(explore&(q>.9)),rows,8,salt);mid=balanced(np.flatnonzero(explore&(q>=.7)&(q<=.9)),rows,8,salt)
    queue=read(base/'tasks.json');known={t['id'] for t in queue};handled=set()
    while len(handled)<len(tasks):
        changed=False
        for task in tasks:
            if task['id'] in handled:continue
            path=ROOT/'analysis/delta_experts'/(task['id']+'.json')
            if not path.exists():continue
            result=read(path);arms=[]
            for fit in result.get('fits',[]):
                for strength in [.25,.5,1.]:
                    spec=dict(fit=fit,strength=strength);arms.append(dict(id='delta_cal_arm_'+digest(spec)[:22],**spec))
            point=base/'points'/(task['id']+'.json')
            if not point.exists():atomic(point,dict(id=task['id'],task=task,arms=arms,panel=failure+high+mid,
                 panel_partitions=dict(failure=failure,high=high,intermediate=mid),seeds=[0,1,2],training_only=True))
            for start in range(0,32,2):
                enqueue=dict(id=task['id']+'_%03d'%start,point=str(point.relative_to(ROOT)),start=start,end=start+2,stage=str(base.relative_to(ROOT)))
                if enqueue['id'] not in known:queue.append(enqueue);known.add(enqueue['id'])
            handled.add(task['id']);changed=True
        if changed:atomic(base/'tasks.json',queue);atomic(base/'producer.json',dict(complete=False,tasks=len(queue),fits_ready=len(handled),time=stamp()))
        if len(handled)<len(tasks):time.sleep(30)
    atomic(base/'producer.json',dict(complete=True,tasks=len(queue),fits_ready=len(handled),time=stamp()))
    print(json.dumps(dict(status='PRODUCED',tasks=len(queue))),flush=True)


if __name__=='__main__':main()
