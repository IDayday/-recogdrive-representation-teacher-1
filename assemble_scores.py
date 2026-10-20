"""Assemble configurable shards in canonical scene order; refuse missing/duplicate scenes."""
from pathlib import Path
import argparse,csv,gzip,json
import numpy as np
ROOT=Path(__file__).resolve().parent
def main(a):
    with gzip.open(ROOT/f'manifests/{a.cohort}.csv.gz','rt') as f:rows=list(csv.DictReader(f))
    if a.subset!='all':rows=[r for r in rows if r['subset']==a.subset]
    if a.limit:rows=rows[:a.limit]
    protocols=[json.loads(p.read_text()) for p in a.input.glob('protocol_rank*.json')]
    if not protocols:raise ValueError('Missing protocol')
    first=protocols[0]
    for p in protocols:
        if any(p[k]!=first[k] for k in ['mode','seeds','methods','cohort','subset']):raise AssertionError('Shard protocols differ')
    data=np.empty((len(first['seeds']),len(rows),len(first['methods'])+1,7))
    for i,row in enumerate(rows):
        path=a.input/'cases'/row['token'];assert (path/'COMPLETE.json').exists(),row['token']
        with np.load(path/'branches.npz') as z:data[:,i]=z['scores']
    a.output.parent.mkdir(parents=True,exist_ok=True);np.save(a.output,data);print('ASSEMBLED',data.shape,a.output)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cohort',choices=['navtest','navtrain'],required=True);p.add_argument('--subset',default='all');p.add_argument('--limit',type=int);main(p.parse_args())
