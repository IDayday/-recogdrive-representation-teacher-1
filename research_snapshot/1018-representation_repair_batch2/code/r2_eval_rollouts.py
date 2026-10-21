"""Prefetched, asynchronously scored intervention sweeps on a rolling subqueue."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

CURSOR={};TASKS={};VERSION={}


def claim_stage(base,worker):
    path=base/'tasks.json'
    if not path.exists():return None
    version=path.stat().st_mtime_ns;key=str(base)
    if VERSION.get(key)!=version:TASKS[key]=read(path);VERSION[key]=version
    index=CURSOR.get(key,0)
    while index<len(TASKS[key]):
        task=TASKS[key][index];index+=1;CURSOR[key]=index
        if (base/'receipts'/(task['id']+'.json')).exists():continue
        folder=base/'claims'/task['id'];folder.parent.mkdir(parents=True,exist_ok=True)
        try:folder.mkdir()
        except FileExistsError:continue
        atomic(folder/'OWNER.json',dict(worker=worker,time=stamp(),pid=os.getpid(),hostname=socket.gethostname()))
        return task
    return None


class Fits:
    def __init__(self):self.data={};self.order=[]
    def get(self,arm):
        import torch
        import numpy as np
        key=arm['fit_path']
        if key not in self.data:
            path=ROOT/key;assert sha(path)==arm['fit_sha256']
            with np.load(path) as z:
                b=np.asarray(z['basis']);assert np.allclose(b.T@b,np.eye(b.shape[1]),atol=1e-3)
                self.data[key]={n:torch.tensor(np.array(z[n]),device='cuda',dtype=torch.float32) for n in z.files}
            self.order.append(key)
            if len(self.order)>64:del self.data[self.order.pop(0)]
        return self.data[key]


@lru_cache(maxsize=1)
def rows():return read(read(ROOT/'manifests/data_source.json')['rows'])


@lru_cache(maxsize=32)
def point(path):return read(path)


def load_case(index):
    from vlm_core import raw_features
    from repair_engine import baseline_row
    began=time.monotonic();row=rows()[index]
    assert row['subset']=='exploration'
    return row,raw_features(row),baseline_row(row),time.monotonic()-began


def evaluate(engine,task,base,pool,fits):
    import torch
    import numpy as np
    from repair_score import score_group
    descriptor=point(str(ROOT/task['point']))
    arms=descriptor['arms'];indices=descriptor['panel'][task['start']:task['end']]
    timing=dict(read_decode_cpu_seconds=0.,input_wait_seconds=0.,inference_submit_seconds=0.,
                device_return_seconds=0.,scoring_wait_seconds=0.,write_seconds=0.)
    pending=[];output=[]
    with ThreadPoolExecutor(max_workers=1) as reader:
        next_case=reader.submit(load_case,indices[0]) if indices else None
        for ix,index in enumerate(indices):
            started=time.monotonic();row,features,reference,read_seconds=next_case.result()
            timing['input_wait_seconds']+=time.monotonic()-started;timing['read_decode_cpu_seconds']+=read_seconds
            if ix+1<len(indices):next_case=reader.submit(load_case,indices[ix+1])
            predictions=[];metrics=[];labels=[];memo=[]
            began=time.monotonic()
            with torch.no_grad():
                hidden=engine.forward_native(features)
                native=[engine.trajectory(features,hidden,seed(row['token'],j)) for j in descriptor['seeds']]
                for j,p in zip(descriptor['seeds'],native):
                    predictions.append(p);metrics.append(p.new_zeros(4));labels.append(('baseline',j))
                for arm in arms:
                    changed,stat=engine.edited(arm,fits.get(arm));hit=None
                    if torch.equal(changed,engine.prefix[arm['block']]):hit=native
                    else:
                        for previous_block,previous,previous_predictions in memo:
                            if previous_block==arm['block'] and previous.shape==changed.shape and torch.equal(previous,changed):hit=previous_predictions;break
                    if hit is None:
                        condition,interface=engine.suffix(arm['block'],changed)
                        hit=[engine.trajectory(features,condition,seed(row['token'],j),interface) for j in descriptor['seeds']]
                        memo.append((arm['block'],changed,hit))
                        if len(memo)>16:memo.pop(0)
                    for j,p in zip(descriptor['seeds'],hit):
                        predictions.append(p);metrics.append(stat);labels.append((arm['id'],j))
                timing['inference_submit_seconds']+=time.monotonic()-began;began=time.monotonic()
                prediction=np.asarray(torch.stack(predictions).float().cpu());statistics=np.asarray(torch.stack(metrics).float().cpu())
                timing['device_return_seconds']+=time.monotonic()-began
            assert np.isfinite(prediction).all() and np.isfinite(statistics).all()
            cap={a['id']:a['cap'] for a in arms};records=[]
            for p,stat,(ident,j) in zip(prediction,statistics,labels):
                relative=float(stat[0]/max(stat[1],1e-12));assert relative<=cap.get(ident,0)+1e-6
                if ident=='baseline' and j==0:assert np.array_equal(p,reference['trajectory'])
                records.append(dict(arm=ident,seed_index=j,seed=seed(row['token'],j),trajectory=p.tolist(),
                                    edit_norm=float(stat[0]),group_norm=float(stat[1]),relative_edit=relative))
            pending.append((pool.submit(score_group,dict(metric_cache=row['metric_cache'],
                    metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)),row,reference))
    for future,row,reference in pending:
        began=time.monotonic();records=future.result(timeout=3600);timing['scoring_wait_seconds']+=time.monotonic()-began
        for record in records:
            if record['arm']=='baseline' and record['seed_index']==0:assert record['score']==reference['score']
            record.update(token=row['token'],session=row['session'],original_S0_quality=row['quality'])
        output.extend(records)
    engine.verify_engine()
    target=base/'results'/(task['id']+'.json');began=time.monotonic()
    atomic(target,dict(status='COMPLETE',time=stamp(),task=task,records=output,timing=timing))
    timing['write_seconds']=time.monotonic()-began
    return dict(path=str(target.relative_to(ROOT)),sha256=sha(target),records=len(output),timing=timing)


def run(engine,parent,pool):
    base=ROOT/parent['stage'];worker=socket.gethostname()+'_'+str(os.getpid());fits=Fits();completed=0
    while True:
        task=claim_stage(base,worker)
        if task is None:
            producer=read(base/'producer.json') if (base/'producer.json').exists() else {}
            if producer.get('complete'):
                if len(list((base/'receipts').glob('*.json')))>=producer['tasks']:
                    return dict(stage=parent['stage'],worker=worker,completed=completed)
            atomic(base/'workers'/(worker+'.json'),dict(status='QUEUE_WAIT',time=stamp(),completed=completed))
            time.sleep(10);continue
        atomic(base/'workers'/(worker+'.json'),dict(status='COMPUTING',time=stamp(),task=task['id'],completed=completed))
        began=time.monotonic()
        result=evaluate(engine,task,base,pool,fits)
        atomic(base/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=task,
               worker=worker,seconds=time.monotonic()-began,result=result))
        completed+=1
