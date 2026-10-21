"""Synthetic end-to-end engineering check; no real representation analysis or model run."""
from common import *
import numpy as np
from subspace_scan_prepare import name

def main(args):
    setup('subspace_scan/synthetic_smoke')
    fake=ROOT/('analysis/subspace_synthetic_engineering_'+args.version);assert not fake.exists();fake.mkdir()
    out=fake/'analysis/subspace_scan_v2';(out/'cache').mkdir(parents=True);n=240;d=80;rng=np.random.default_rng(20261016)
    meta=[dict(token=f'fake{i}',session=f'synthetic_session_{i//8}',subset='exploration' if i<192 else 'validation',quality='failure' if i%2 else 'high_quality',baseline_pdms_100=50 if i%2 else 99) for i in range(n)]
    q=np.array([r['baseline_pdms_100']/100 for r in meta]);x=rng.normal(size=(n,d));x[:,0]+=(q<.7)*1.5
    atomic(out/'natural_metadata.json',meta);atomic(out/'paired_metadata.json',meta)
    src=fake/'analysis/natural_route1_v1';src.mkdir();np.save(src/'scores.npy',q)
    for label,mask in [('high_quality',(q>.9)&(np.arange(n)<192)),('failure',(q<.7)&(np.arange(n)<192))]:
        f=src/'moments'/('exploration__'+label);f.mkdir(parents=True);np.save(f/'n.npy',np.array(mask.sum()))
        for field,value in [('sum',x[mask].sum(0)),('gram',x[mask].T@x[mask])]:
            a=np.zeros((1,1,1)+value.shape);a[0,0,0]=value;np.save(f/('representations_'+field+'.npy'),a)
    paired=np.stack([np.stack([x,x+np.r_[2.,np.zeros(d-1)]],axis=1),np.stack([x+.05*rng.normal(size=x.shape),x+np.r_[2.,np.zeros(d-1)]+.05*rng.normal(size=x.shape)],axis=1)])
    pq=np.tile([.99,.5],(2,n,1));np.save(out/'cache/r2_a0_scores.npy',pq)
    tasks=[dict(phase='cv',route='r1',start=-1,step=0,layer=0,token=0,id='synthetic_natural'),dict(phase='cv',route='r2',start=0,step=4,layer=0,token=0,id='synthetic_paired')];cells={}
    for task,a in zip(tasks,[x.astype(np.float32),paired.astype(np.float32)]):
        cell=name(task['route'],task['start'],task['step'],0,0);path=out/'cache'/(cell+'.npy');np.save(path,a);cells[cell]=dict(sha256=sha(path),shape=list(a.shape))
    # Sufficient statistics must match float32 stored representation values, exactly as production.
    x=x.astype(np.float32).astype(np.float64)
    for label,mask in [('high_quality',(q>.9)&(np.arange(n)<192)),('failure',(q<.7)&(np.arange(n)<192))]:
        f=src/'moments'/('exploration__'+label)
        for field,value in [('sum',x[mask].sum(0)),('gram',x[mask].T@x[mask])]:
            a=np.zeros((1,1,1)+value.shape);a[0,0,0]=value;np.save(f/('representations_'+field+'.npy'),a)
    atomic(out/'CACHE_INDEX.json',dict(cells=cells));import subspace_scan_cv as cv
    cv.ROOT=fake;cv.OUT=out;records=[]
    for task in tasks:
        doc=cv.scan(task);assert len(doc['search'])==1346 and not doc['heldout_validation_evaluated'];atomic(fake/(task['id']+'.json'),doc);records.append(doc)
    # Freeze a small region and controls, then exercise held-out confirmation separately.
    from subspace_scan_math import configs
    ids=[i for i,c in enumerate(configs()) if (c['kind']=='residual' and c['ks']==8 and c['kf']==8 and c['r']==8) or (c['kind']=='random' and c['r']==8 and c['replicate']==0) or c['kind']=='full']
    lock=dict(cells={doc['cell']:[dict(centering=c,index=i,regions=['synthetic'],comparison_roles=['smoke'],diagnostic_only=False) for c in ['uncentered','pooled_centered'] for i in ids] for doc in records})
    atomic(out/'FROZEN_CONFIRMATION.json',lock);import subspace_scan_confirm as confirm
    confirm.ROOT=fake;confirm.OUT=out
    for task in tasks:
        t=dict(task,phase='confirm',selection_sha256=sha(out/'FROZEN_CONFIRMATION.json'));doc=confirm.confirm(t,'cpu_float64');assert doc['status']=='COMPLETE' and len(doc['results'])==6
        atomic(fake/(task['id']+'_confirmation.json'),doc)
    atomic(ROOT/'provenance/SUBSPACE_SYNTHETIC_INTEGRATION.json',dict(status='PASS',time=stamp(),path=str(fake),real_data_used=False,cells=2,centers=2,folds=5,search_variants_per_cell=1346))
    print('SYNTHETIC FULL-CV / RANK / P0-P1 / FROZEN-CONFIRMATION PASS',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--version',default='v1');main(p.parse_args())
