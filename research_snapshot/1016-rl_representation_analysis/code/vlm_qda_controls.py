"""Same-readout space controls and neighboring ranks at four CV-frozen sites.

No model collection or policy selection changes. Every planned control is
reported, including three random bases, full dimension and all nearby ranks.
"""
from common import *
import argparse
import numpy as np
from scipy.linalg import cho_factor,cho_solve
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_scan import metadata,moment,subtract,metric_dict,save_npz
from vlm_space import class_geometry,random_bases,metrics
from vlm_selection import score
from repair_queue_v2 import atomic_unique as atomic
OUT=VOUT/'qda_controls'

def configs():
    return [dict(kind=kind,r=r,replicate=j) for r in [64,96,128,192,256] for kind,j in [('success_pca',None),('random',0),('random',1),('random',2)]]+[dict(kind='full',r=None,replicate=None)]

def prepare():
    assert not (OUT/'PROTOCOL.json').exists();choices={}
    for path in (VOUT/'development/completed_fits').glob('*.json'):
        obj=read(path);f=obj['fit']
        if f['config']['kind']!='success_pca128_shrink_qda':continue
        c=next((v for v in ['vision','bridge','interface'] if f['block'].startswith(v)),'language')
        if c not in choices or score(f['spec'])>score(choices[c]['fit']['spec']):choices[c]=obj
    assert set(choices)=={'vision','bridge','language','interface'}
    sites=[dict(component=c,fit=o['fit'],source_existing_confirmation=o['confirmation']['id']) for c,o in sorted(choices.items())]
    atomic(OUT/'PROTOCOL.json',dict(status='FROZEN_BEFORE_CONTROLS',time=stamp(),sites=sites,configs=configs(),
        selection='One existing QDA site per component chosen ONLY by frozen exploration CV score, never by hold-out performance.',
        fit='Same full exploration class moments and fixed five session folds; same 5% isotropic shrink-QDA across all spaces.',
        evaluation='Same exploration evaluation cohort, full session-held-out extremes, S1/S2 conditional on S0 extreme cohort.',
        no_policy_selection_or_intervention_changed=True,additional_confirmation_tests=80,combined_planned_confirmation_bound=1000,
        cv_correction='Joint exploratory BH/BY with original full planned bound plus84; final supplementary correction must refresh after main snapshots.',
        code_sha256=sha(Path(__file__))))
    print('QDA_CONTROL_PROTOCOL_FROZEN',flush=True)

def fit_probe(mom,g,cfg,seed_value):
    us,es,uf,ef,rs,rf,ms,mf,center,cov=g;d=len(ms);r=cfg['r']
    if cfg['kind']=='success_pca':
        if r>rs:return None
        b=us[:,:r]
    elif cfg['kind']=='random':
        if r>d:return None
        b=random_bases(d,seed_value)[cfg['replicate']][:,:r]
    else:b=np.eye(d)
    means=[ms@b,mf@b];factors=[]
    for n,mean,gram in [(mom[0][0],ms,mom[0][2]),(mom[1][0],mf,mom[1][2])]:
        c=b.T@(gram/n-np.outer(mean,mean))@b;scale=max(float(np.trace(c)/len(c)),1e-10);c=.95*c+.05*scale*np.eye(len(c));factors.append(cho_factor(c,check_finite=False))
    return b,means,factors

def predict(x,probe):
    if probe is None:return np.full(len(x),np.nan)
    basis,means,factors=probe;z=np.asarray(x,dtype=np.float64)@basis;ll=[]
    for mean,cf in zip(means,factors):
        diff=z-mean;ll.append(-.5*((diff*cho_solve(cf,diff.T,check_finite=False).T).sum(1)+2*np.log(np.diag(cf[0])).sum()))
    return ll[1]-ll[0]

def process(site):
    f=site['fit'];cell=f['cell'];dest=OUT/'results'/(cell+'.json')
    if dest.exists():return read(dest)
    rows,q,exp,fold,sessions,high=metadata();proof=read(ROOT/f['cell_proof_path']);assert sha(ROOT/proof['path'])==proof['sha256'];x=np.load(ROOT/proof['path'],mmap_mode='r');valid=np.isfinite(x[:,0]);extreme=(q<.7)|(q>.9);fit=exp&valid&extreme
    ev=exp&valid&(q<.7);ev[high[valid[high]][:8192]]=True;idx=np.flatnonzero(ev);locations=np.full(len(rows),-1,dtype=int);locations[idx]=np.arange(len(idx));entries=configs()
    held=[[moment(x,fit&(fold==k)&mask) for mask in [q>.9,q<.7]] for k in range(5)];totals=[tuple(sum(h[i][j] for h in held) for j in range(3)) for i in range(2)];centered=f['centering']=='pooled_centered';seed_value=int(digest(dict(cell=cell,vlm_space_root=20261016))[:16],16)
    oof=np.full((len(idx),len(entries)),np.nan);fold_metrics=[]
    for k in range(5):
        mom=[subtract(t,h) for t,h in zip(totals,held[k])];g=class_geometry(mom,centered);test=ev&(fold==k);at=locations[np.flatnonzero(test)];a=np.asarray(x[test],dtype=np.float64)
        for i,cfg in enumerate(entries):oof[at,i]=predict(a,fit_probe(mom,g,cfg,seed_value))
        fold_metrics.append(metrics(oof[at],q[test]<.7,sessions[test],high_population=int((fit&(fold==k)&(q>.9)).sum())))
    cv=metrics(oof,q[idx]<.7,sessions[idx],high_population=int((fit&(q>.9)).sum()));fold_metrics=np.asarray(fold_metrics)
    # The parent PCA128 quadratic readout must reproduce the original scan.
    original=read(VOUT/'rapid/results'/(cell+'.json'));cc=int(centered)
    with np.load(ROOT/original['array_path']) as a:expected=np.array(a['secondary_metrics'][cc,5,1])
    parent_index=next(i for i,c in enumerate(entries) if c['kind']=='success_pca' and c['r']==128)
    assert np.allclose(cv[parent_index],expected,rtol=1e-5,atol=1e-7,equal_nan=True),(cell,cv[parent_index],expected)
    val=np.flatnonzero((~exp)&valid&extreme);g=class_geometry(totals,centered);validation=np.column_stack([predict(np.asarray(x[val],dtype=np.float64),fit_probe(totals,g,cfg,seed_value)) for cfg in entries]);vm=metrics(validation,q[val]<.7,sessions[val]);base=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')[:,:,0,0];records=[]
    for i,cfg in enumerate(entries):
        noise=[]
        for j in [1,2]:
            keep=(base[j,val]<.7)|(base[j,val]>.9);noise.append(dict(seed_index=j,metrics=metric_dict(metrics(validation[keep,i],base[j,val[keep]]<.7,sessions[val[keep]])[0])))
        identity='qda_control_'+digest(dict(cell=cell,centering=f['centering'],config=cfg))[:20];record=dict(id=identity,cell=cell,config=cfg,cv=metric_dict(cv[i]),cv_fold_min=float(np.nanmin(fold_metrics[:,i,0])),heldout=metric_dict(vm[i]),secondary_seeds=noise)
        records.append(record)
        if i!=parent_index:
            confirmation=dict(status='COMPLETE',time=stamp(),id=identity,cell=cell,fit_sha256=proof['sha256'],cases=len(val),metrics=record['heldout'],secondary_seeds=noise,
                scope='All prospectively frozen quadratic space/dimension controls; no policy selection changes.',control_protocol_sha256=sha(OUT/'PROTOCOL.json'),test_accessed=False,validation_used_for_fit=False)
            p=VOUT/'confirmation'/(identity+'.json')
            if not p.exists():atomic(p,confirmation)
    arrays=OUT/'arrays'/(cell+'.npz');h=save_npz(arrays,cv_metrics=cv,fold_metrics=fold_metrics,validation_metrics=vm,oof=oof,evaluation_indices=idx,validation_indices=val,validation_scores=validation)
    result=dict(status='PASS',time=stamp(),site=site,source_sha256=proof['sha256'],records=records,array_path=str(arrays.relative_to(ROOT)),array_sha256=h,original_parent_cv_reproduced=True,no_model_or_test_access=True,policy_selection_unchanged=True);atomic(dest,result);return result

def main(a):
    setup('vlm_repair/qda_controls')
    if a.mode=='prepare':prepare();return
    assert os.cpu_count()>=160
    with threadpool_limits(4):
        for site in read(OUT/'PROTOCOL.json')['sites'][a.node::2]:process(site);print('QDA_CONTROL_SITE_PASS',site['fit']['cell'],flush=True)
    atomic(OUT/f'node{a.node}_COMPLETE.json',dict(status='PASS',time=stamp()))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','node']);p.add_argument('--node',type=int);main(p.parse_args())
