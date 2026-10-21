"""Keep unavailable privileged donors in coverage while reporting donor-available diagnostics separately."""
from common import *
import argparse
import numpy as np

def main(args):
    setup('repair/reference_analysis')
    base=ROOT/'runs'/read(ROOT/'repair_v1/ACTIVE_RUN.json')['run'];folder=ROOT/'repair_v1/analysis'/args.stage
    rows=read(folder/'rows.json');arms=read(folder/'arms.json');data=np.load(folder/'scores.npy',mmap_mode='r');available={}
    for path in sorted((base/'results').glob(args.stage+'_s*.json')):
        for r in read(path)['records']:
            if r['arm']=='baseline':continue
            present=bool(r['reference_available'])
            if r['token'] in available:assert available[r['token']]==present
            available[r['token']]=present
    mask=np.array([available[r['token']] for r in rows]);records=[]
    for i,a in enumerate(arms,1):
        baseline=data[:,mask,0,0];edited=data[:,mask,i,0];failed=baseline<.7
        records.append(dict(arm=a,available_cases=int(mask.sum()),natural_failures=int(failed.sum()),
            repaired_ge70=int((failed&(edited>=.7)).sum()),repaired_gt90=int((failed&(edited>.9)).sum()),
            mean_delta_on_available_pdms=float((edited-baseline).mean()*100) if mask.any() else None))
    target=folder/'REFERENCE_COVERAGE.json';assert not target.exists()
    atomic(target,dict(status='COMPLETE',time=stamp(),all_cases=len(rows),available=int(mask.sum()),unavailable=int((~mask).sum()),
        source='Same-scene exploration/validation P0 final-scored candidate above 90; no donor means identity.',
        diagnostic_only=True,deployable=False,records=records))
    print(json.dumps(dict(status='COMPLETE',stage=args.stage,available=int(mask.sum()),total=len(rows))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
