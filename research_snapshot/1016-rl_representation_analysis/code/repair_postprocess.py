"""CPU-only simple trajectory-scale control, reusing the freshly evaluated RL baselines."""
from common import *
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import multiprocessing as mp
import numpy as np

def scale_trajectory(trajectory,factor):
    p=np.asarray(trajectory,dtype=np.float32).copy()
    p[:,:2]*=np.float32(factor)
    p[:,0]=np.clip(p[:,0],np.float32(-1.57),np.float32(65.17))
    p[:,1]=np.clip(p[:,1],np.float32(-19.68),np.float32(22.32))
    return p

def init_control(output):
    from score import init_scorer
    init_scorer()
    global CONTROL_ROWS,CONTROL_CFG,CONTROL_ARMS
    path=Path(output)/'stages/postprocess_validation'
    CONTROL_ROWS={r['token']:r for r in read(path/'panel.json')}
    CONTROL_CFG=read(ROOT/'configs/baseline.json');CONTROL_ARMS=read(path/'arms.json')

def process(payload):
    source,output=payload;rows=CONTROL_ROWS;cfg=CONTROL_CFG;arms=CONTROL_ARMS
    from repair_score import score_group
    from repair_engine import geometries
    doc=read(source);original=doc['task'];task=dict(original,id=original['id'].replace('validation_baseline','postprocess_validation'),stage='postprocess_validation')
    records=[]
    for b in doc['records']:
        assert b['arm']=='baseline';token=b['token'];base=np.array(b['trajectory'],dtype=np.float32);candidates=[]
        for a in arms:
            pred=scale_trajectory(base,a['factor']);r=dict(b,arm=a['id'],trajectory=pred.tolist(),edit=dict(relative_edit_max=0.,gate_mean=1.),geometry=geometries(pred,base))
            candidates.append(r)
        task_scores=dict(metric_cache=rows[token]['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=candidates)
        scored=score_group(task_scores);records.append(b);records.extend(scored)
    path=output/'results'/f'{task["id"]}.json';atomic(path,dict(status='COMPLETE',time=stamp(),task=task,records=records,compute='DSW CPU only'))
    atomic(output/'receipts'/path.name,dict(status='COMPLETE',time=stamp(),task=task,result_sha256=sha(path),records=len(records)))
    return len(records)

def main(args):
    setup('repair/postprocess');compatibility()
    from score import init_scorer
    source=ROOT/'runs'/args.source_run;output=ROOT/'runs/repair_postprocess_v1';name='postprocess_validation'
    protocol=read(source/'stages/validation_baseline/PROTOCOL.json')
    while len(list((source/'receipts').glob('validation_baseline_s*.json')))<protocol['tasks']:time.sleep(30)
    panel=read(source/'stages/validation_baseline/panel.json');rows={r['token']:r for r in panel};cfg=read(ROOT/'configs/baseline.json')
    arms=[dict(id=f'trajectory_scale_{factor}',method='trajectory_scale',factor=factor,source='action_space_control') for factor in [.99,1.005,1.01,1.02]]
    stage=output/'stages'/name;stage.mkdir(parents=True,exist_ok=True)
    if not (stage/'PROTOCOL.json').exists():
        atomic(stage/'panel.json',panel);atomic(stage/'arms.json',arms)
        atomic(stage/'PROTOCOL.json',dict(protocol,stage=name,arms=len(arms),reason='Check whether apparent representation gains reduce to uniformly changing progress; no test data or new model'))
    jobs=[]
    for p in sorted((source/'results').glob('validation_baseline_s*.json')):
        target=output/'receipts'/p.name.replace('validation_baseline','postprocess_validation')
        if not target.exists():jobs.append((p,output))
    completed=0;iterator=iter(jobs);began=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=mp.get_context('spawn'),initializer=init_control,initargs=(str(output),)) as pool:
        pending={}
        for _ in range(args.workers*2):
            item=next(iterator,None)
            if item is not None:pending[pool.submit(process,item)]=item[0]
        while pending:
            finished,_=wait(pending,return_when=FIRST_COMPLETED)
            for f in finished:
                f.result();pending.pop(f);completed+=1
                item=next(iterator,None)
                if item is not None:pending[pool.submit(process,item)]=item[0]
            if completed%25==0:
                atomic(output/'STATUS.json',dict(status='SCORING',time=stamp(),completed=completed,total=len(jobs),seconds=time.monotonic()-began))
                print(json.dumps(dict(completed=completed,total=len(jobs))),flush=True)
    from repair_analysis import summarize,safety
    summary=summarize(output,name);safety(name)
    atomic(output/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),arms=len(arms),records=summary['records'],workers=args.workers))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=4);p.add_argument('--source-run',default='repair_20261016_v2');main(p.parse_args())
