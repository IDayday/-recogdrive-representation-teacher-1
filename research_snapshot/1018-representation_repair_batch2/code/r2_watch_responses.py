"""One-stage mechanical compact-response producer; safe restart deduplication."""
from r2_common import *
import argparse


def main(args):
    base=ROOT/args.stage;queued=set();handler='code/r2_point_response.py';version=sha(ROOT/handler)
    ledger=ROOT/'analysis/responses'/base.name/'QUEUED.json'
    if ledger.exists():queued=set(read(ledger)['points'])
    while True:
        tasks=[]
        for point in sorted((base/'points').glob('*.json')):
            if point.stem in queued:continue
            d=read(point);chunks=[point.stem+'_'+str(i).zfill(args.digits) for i in range(0,len(d['panel']),args.chunk)]
            if not all((base/'receipts'/(i+'.json')).exists() for i in chunks):continue
            spec=dict(stage=args.stage,point=str(point.relative_to(ROOT)),point_id=point.stem,chunks=chunks)
            tasks.append(dict(id='outcome_matrix_'+digest(spec)[:24],handler=handler,handler_sha256=version,**spec));queued.add(point.stem)
        if tasks:
            append('cpu',tasks);atomic(ledger,dict(time=stamp(),points=sorted(queued)))
        p=base/'producer.json'
        if p.exists():
            state=read(p)
            if state.get('complete') and len(list((base/'receipts').glob('*.json')))>=state['tasks']:
                print(json.dumps(dict(status='ALL_POINTS_QUEUED',stage=args.stage,points=len(queued))),flush=True);return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--chunk',type=int,default=4)
    p.add_argument('--digits',type=int,default=3);main(p.parse_args())
