"""Checkpointed, targeted CV readouts from existing representations only.

Uses the original geometry and residual construction. Expensive per-cell fold
statistics and eigenspaces are durable and shared across requested candidates.
No model inference, validation fitting or test access occurs here.
"""
from common import *
import argparse, fcntl
import numpy as np
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_scan import metadata, moment, subtract, metrics, metric_dict, save_npz
from vlm_space import class_geometry, residual
from vlm_fold_backup_v2 import fingerprint, unpack
from repair_queue_v2 import atomic_unique as atomic

DEST=VOUT/'late_token_coverage'


def working(cell):
    proof=read(VOUT/'cells'/(cell+'.json'))
    inputs=dict(source=proof['sha256'],manifest=sha(ROOT/'manifests/natural_s0.json'),
                scores=sha(ROOT/'analysis/natural_route1_v1/scores.npy'),
                geometry=sha(ROOT/'code/vlm_space.py'),folds=sha(ROOT/'code/vlm_scan.py'))
    folder=DEST/'work'/(cell+'_'+digest(inputs)[:16])
    folder.mkdir(parents=True,exist_ok=True)
    return proof,folder


def moments(cell):
    proof,folder=working(cell)
    rows,q,exp,fold,sessions,high=metadata()
    with (folder/'moments.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        marker=folder/'MOMENTS_READY.json'
        if not marker.exists():
            assert sha(ROOT/proof['path'])==proof['sha256']
            x=np.load(ROOT/proof['path'],mmap_mode='r')
            valid=np.isfinite(x[:,0]);fit=exp&valid&((q<.7)|(q>.9))
            for k in range(5):
                path=folder/f'held{k}.npz'
                if path.exists():continue
                groups=[moment(x,fit&(fold==k)&mask) for mask in [q>.9,q<.7]]
                save_npz(path,ns=groups[0][0],ss=groups[0][1],gs=groups[0][2],
                         nf=groups[1][0],sf=groups[1][1],gf=groups[1][2])
            atomic(marker,dict(status='READY',time=stamp(),cell=cell,source_sha256=proof['sha256'],
                   manifest_sha256=sha(ROOT/'manifests/natural_s0.json'),
                   held_sha256={f'held{k}.npz':sha(folder/f'held{k}.npz') for k in range(5)}))
        meta=read(marker)
        assert meta['source_sha256']==proof['sha256']
        assert meta['manifest_sha256']==sha(ROOT/'manifests/natural_s0.json')
        held=[]
        for k in range(5):
            p=folder/f'held{k}.npz';assert sha(p)==meta['held_sha256'][p.name]
            with np.load(p) as z:held.append(unpack(z))
    total=[tuple(sum(h[group][field] for h in held) for field in range(3)) for group in range(2)]
    return proof,folder,total,held


def geometry(folder,mom,centered,k):
    path=folder/f'geometry_c{int(centered)}f{k}.npz'
    with (folder/(path.stem+'.lock')).open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        key=fingerprint(mom)
        if not path.exists():
            value=class_geometry(mom,centered)
            save_npz(path,**{f'g{i:02d}':v for i,v in enumerate(value)},fingerprint=np.asarray(key))
            atomic(path.with_suffix('.json'),dict(status='READY',time=stamp(),sha256=sha(path),
                    input_fingerprint=key,original_geometry_code_sha256=sha(ROOT/'code/vlm_space.py')))
        assert sha(path)==read(path.with_suffix('.json'))['sha256']
        with np.load(path) as z:
            assert str(z['fingerprint'].item())==key
            return tuple(int(z[f'g{i:02d}']) if i in [4,5] else np.array(z[f'g{i:02d}']) for i in range(10))


def direction(g,cfg):
    us,es,uf,ef,rs,rf,ms,mf,center,cov=g
    basis,s,rank=residual(us,uf,ef,cfg['ks'],cfg['kf'],cfg['kind']=='variance_residual')
    r=cfg['r'];assert basis is not None and rank>=r
    degen=bool(r<len(s) and abs(s[r-1]-s[r])<=max(float(s[0]),1.)*1e-8)
    prefix=np.cumsum(basis*(basis.T@(mf-ms))[None,:],axis=1)
    w=prefix[:,r-1];variance=float((w*(cov@w)).sum())
    assert variance>1e-24 and np.linalg.norm(w)>1e-12
    return w/np.sqrt(variance),(ms+mf)*.5,[rs,rf,rank],degen


def qualify(cell,config_index,centered):
    original=read(VOUT/'scan/results'/(cell+'.json'))
    assert original['status']=='COMPLETE'
    entries=read(VOUT/'scan/CONFIGS.json');cfg=entries[config_index]
    assert cfg['kind'] in ['basis_residual','variance_residual']
    identity=digest(dict(cell=cell,config=cfg,centered=centered,source_result_sha256=sha(VOUT/'scan/results'/(cell+'.json'))))[:24]
    output=DEST/'qualifications'/(identity+'.json')
    if output.exists():
        previous=read(output);assert previous['code_sha256']==sha(Path(__file__))
        return previous
    with np.load(ROOT/original['array_path']) as z:
        indices=np.array(z['evaluation_indices']);expected=np.array(z['metrics'][int(centered),:,config_index,:])
        expected_ranks=np.array(z['ranks'][int(centered),:,config_index,:])
        assert (z['status'][int(centered),:,config_index]==0).all()
        assert not z['cutoff_degenerate'][int(centered),:,config_index].any()
    proof,folder,total,held=moments(cell)
    x=np.load(ROOT/proof['path'],mmap_mode='r');rows,q,exp,fold,sessions,high=metadata()
    valid=np.isfinite(x[:,0]);fit=exp&valid&((q<.7)|(q>.9))
    oof=np.full(len(indices),np.nan);actual=np.full_like(expected,np.nan);ranks=[]
    for k in range(5):
        train=[subtract(t,h) for t,h in zip(total,held[k])]
        g=geometry(folder,train,bool(centered),k)
        w,c,rank,degen=direction(g,cfg);assert not degen
        assert np.array_equal(rank,expected_ranks[k])
        use=fold[indices]==k;a=np.asarray(x[indices[use]],dtype=np.float64)
        oof[use]=(a-c)@w
        high_pop=int((fit&(fold==k)&(q>.9)).sum())
        actual[k]=metrics(oof[use],q[indices[use]]<.7,sessions[indices[use]],high_population=high_pop)[0]
        ranks.append(rank)
    assert np.isfinite(oof).all()
    high_pop=int((fit&(q>.9)).sum())
    actual[5]=metrics(oof,q[indices]<.7,sessions[indices],high_population=high_pop)[0]
    assert np.allclose(actual,expected,rtol=1e-6,atol=1e-6,equal_nan=True),float(np.nanmax(abs(actual-expected)))
    baseline=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')[:,:,0,0]
    assert np.array_equal(baseline[0],q)
    sw=np.where(q[indices]<.7,1.,high_pop/max(int((q[indices]>.9).sum()),1));noise=[]
    for j in [1,2]:
        keep=(baseline[j,indices]<.7)|(baseline[j,indices]>.9)
        values=metrics(oof[keep],baseline[j,indices[keep]]<.7,sessions[indices[keep]],sample_weight=sw[keep])[0]
        noise.append(dict(seed_index=j,metrics=metric_dict(values)))
    result=dict(status='QUALIFIED_NUMERIC_READOUT',time=stamp(),cell=cell,config_index=config_index,config=cfg,
            centering='pooled_centered' if centered else 'uncentered',source_result_sha256=sha(VOUT/'scan/results'/(cell+'.json')),
            source_array_sha256=original['array_sha256'],other_sampling_seeds=noise,
            maximum_S0_metric_difference=float(np.nanmax(abs(actual-expected))),ranks=ranks,
            S0_fold_and_pooled_metrics=actual.tolist(),existing_training_representations_only=True,
            no_model_collection=True,test_accessed=False,validation_used_for_qualification=False,
            code_sha256=sha(Path(__file__)))
    atomic(output,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cell',required=True);p.add_argument('--config-index',type=int,required=True)
    p.add_argument('--centered',type=int,choices=[0,1],required=True);p.add_argument('--threads',type=int,default=2);a=p.parse_args()
    setup('vlm_repair/late_qualification')
    with threadpool_limits(a.threads):
        result=qualify(a.cell,a.config_index,a.centered)
    print('LATE_TARGETED_READOUT_PASS',result['cell'],result['config_index'],result['maximum_S0_metric_difference'],flush=True)
