"""Queue response reductions only after every chunk of a point has completed."""
from r2_common import *


def main():
    stages=[('representation_coarse_v1',4,3),('fold_and_outcome_probes_v1',2,2),('learned_calibration_eval_v1',4,3)]
    queued=set();handler='code/r2_point_response.py';version=sha(ROOT/handler)
    while True:
        tasks=[]
        for name,size,digits in stages:
            base=ROOT/'runs'/name
            for path in sorted((base/'points').glob('*.json')):
                key=(name,path.stem)
                if key in queued:continue
                point=read(path);chunks=[path.stem+'_'+str(start).zfill(digits) for start in range(0,len(point['panel']),size)]
                if not all((base/'receipts'/(c+'.json')).exists() for c in chunks):continue
                spec=dict(stage=str(base.relative_to(ROOT)),point=str(path.relative_to(ROOT)),point_id=path.stem,chunks=chunks)
                tasks.append(dict(id='outcome_matrix_'+digest(spec)[:24],handler=handler,handler_sha256=version,**spec));queued.add(key)
        if tasks:
            append('cpu',tasks)
            atomic(ROOT/'analysis/responses/PRODUCER.json',dict(status='MONITORING',time=stamp(),points_queued=len(queued),last_batch=len(tasks)))
        if all((ROOT/'runs'/n/'producer.json').exists() and read(ROOT/'runs'/n/'producer.json').get('complete') and
               len(list((ROOT/'runs'/n/'receipts').glob('*.json')))>=read(ROOT/'runs'/n/'producer.json')['tasks'] for n,_,_ in stages):
            atomic(ROOT/'analysis/responses/PRODUCER_COMPLETE.json',dict(status='COMPLETE',time=stamp(),points_queued=len(queued)))
            print(json.dumps(dict(status='COMPLETE',points_queued=len(queued))),flush=True);return
        time.sleep(60)


if __name__=='__main__':main()
