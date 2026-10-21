"""Session-CV representatives, dimensional neighborhoods and independent validation readouts."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_scan import metadata,metric_dict,save_npz
from vlm_space import metrics
from repair_queue_v2 import atomic_unique as atomic

BANDS=[(0,16),(17,128),(129,99999)]

def finite(value,default=0.):return default if value is None else float(value)

def score(record):
    m=record['metrics'];auc=finite(m['auc'],.5);spread=finite(record.get('auc_fold_std'),1.);minimum=finite(record.get('auc_fold_min'),.5)
    return auc-.25*spread-.10*max(0.,.6-minimum)

_NEIGHBOR_CACHE={}
def neighbor_indices(config,entries):
    def key(c):return (c['kind'],c.get('ks'),c.get('kf'),c.get('r'),c.get('replicate'))
    if len(entries) not in _NEIGHBOR_CACHE:
        lookup={key(c):i for i,c in enumerate(entries)};grids={}
        for kind in {c['kind'] for c in entries}:
            for field in ['ks','kf','r']:
                grids[(kind,field)]=sorted({c[field] for c in entries if c['kind']==kind and c.get(field) is not None})
        _NEIGHBOR_CACHE[len(entries)]=(lookup,grids)
    lookup,grids=_NEIGHBOR_CACHE[len(entries)];kind=config['kind'];out=[]
    if kind not in ['basis_residual','variance_residual','success_pca','failure_pca']:return out
    for field in (['r'] if kind in ['success_pca','failure_pca'] else ['ks','kf','r']):
        values=grids[(kind,field)];at=values.index(config[field])
        for j in [at-1,at+1]:
            if j<0 or j>=len(values):continue
            candidate=dict(config);candidate[field]=values[j]
            if kind.endswith('residual'):
                if config.get('equal') and field in ['ks','kf']:candidate['ks']=candidate['kf']=values[j]
                if (candidate['ks']==candidate['kf'])!=config.get('equal'):continue
            found=lookup.get(key(candidate))
            if found is not None:out.append(found)
    return sorted(set(out))


def block_candidates(block,analysis_root=None,primary='rapid',sources=None):
    dr=analysis_root or VOUT
    plan=next(b for b in read(dr/'PIVOT_PLAN.json')['blocks'] if b['name']==block);paths=[dr/(primary+'/results')/(block+'__'+group+'.json') for group in plan['groups']]
    if not all(p.exists() for p in paths):return None
    records=[]
    for route in (sources or ['rapid','scan']):
        entries=read(dr/route/'CONFIGS.json')
        for group in plan['groups']:
            path=dr/route/'results'/(block+'__'+group+'.json')
            if not path.exists():continue
            result=read(path)
            if result['status']!='COMPLETE':continue
            with np.load(ROOT/result['array_path']) as data:
                matrix_metrics=np.array(data['metrics']);result_hash=sha(path)
                for rec in result['shortlisted']:
                    if rec['config']['kind'] not in ['basis_residual','variance_residual','success_pca','failure_pca','full','success_pca128_shrink_qda'] or rec.get('cutoff_degenerate_any'):continue
                    if 'config_index' not in rec and rec['config']['kind']!='success_pca128_shrink_qda':continue
                    if rec['metrics']['auc'] is None:continue
                    cc=int(rec['centering']=='pooled_centered');neighbors=neighbor_indices(rec['config'],entries) if 'config_index' in rec else []
                    values=matrix_metrics[cc,5,neighbors,0] if neighbors else np.array([]);near=values[np.isfinite(values)]
                    support=int((near>=max(.55,rec['metrics']['auc']-.03)).sum())
                    item=dict(rec,cell=result['cell'],block=block,group=group,analysis_source=route,source_result_sha256=result_hash,moment=dict(path=result['moment_path'],sha256=result['moment_sha256']),cell_proof_path=str((dr/'cells'/(result['cell']+'.json')).relative_to(ROOT)),
                        neighbor_tested=int(len(near)),neighbor_supported=support,neighbor_auc=near.tolist())
                    noise=rec.get('other_sampling_seeds',[])
                    stable=finite(rec['auc_fold_min'])>.55 and finite(rec['metrics']['session_positive_fraction'])>=.65 and all(finite(n['metrics']['auc'])>.55 for n in noise)
                    item['stable_cv_region']=bool(stable and rec['metrics']['auc']>=.6 and support>=1)
                    records.append(item)
    selected=[]
    for lo,hi in BANDS:
        group=[r for r in records if lo<=int(r['config']['r'] or 0)<=hi and r['config']['kind'] not in ['full','success_pca128_shrink_qda']]
        if not group:continue
        group.sort(key=lambda r:(r['stable_cv_region'],score(r),r['neighbor_supported']),reverse=True);selected.append(dict(group[0],rank_band=[lo,hi]))
    # Preserve a strong variance-only QDA readout even when mean-gap probes are weak.
    qda=[r for r in records if r['config']['kind']=='success_pca128_shrink_qda']
    if qda:
        qda.sort(key=score,reverse=True);selected.append(dict(qda[0],rank_band='qda_secondary'))
    # Mean-gap full-dimensional diagnostic is a separate control family.
    full=[r for r in records if r['config']['kind']=='full']
    if full:
        full.sort(key=score,reverse=True);selected.append(dict(full[0],rank_band='full'))
    return dict(status='FROZEN_DEVELOPMENT_BLOCK',time=stamp(),block=block,all_rapid_cells_completed=True,
        target_full_grid_cells=len(plan['groups']),full_grid_cells_available=sum((dr/'scan/results'/(block+'__'+g+'.json')).exists() for g in plan['groups']),
        selected=selected,analysis_only=True,full_grid_pending_does_not_imply_exhaustive_selection=True,rule='best stable dimensional neighborhood per rank band; otherwise explicitly diagnostic representative; one separate full-D control')

def confirm(fit):
    path=VOUT/'confirmation'/(fit['id']+'.json')
    if path.exists():return read(path)
    proof=read(ROOT/fit['cell_proof_path']);x=np.load(ROOT/proof['path'],mmap_mode='r');rows,q,exp,fold,sessions,_=metadata();use=(~exp)&np.isfinite(x[:,0])&((q<.7)|(q>.9));indices=np.flatnonzero(use)
    with np.load(ROOT/fit['path']) as f:
        b=np.asarray(f['basis'],dtype=np.float64);center=np.asarray(f['center'],dtype=np.float64);mh=np.asarray(f['mh'],dtype=np.float64);mf=np.asarray(f['mf'],dtype=np.float64)
        w=b@(mf-mh);mid=center+b@((mh+mf)*.5);v=(np.asarray(x[indices],dtype=np.float64)-mid)@w
        if fit['config']['kind']=='success_pca128_shrink_qda':
            z=(np.asarray(x[indices],dtype=np.float64)-center)@b;ds=z-mh;df=z-mf
            v=.5*((ds*(ds@f['cov_inv_s'])).sum(1)-(df*(df@f['cov_inv_f'])).sum(1))
    # Standardized gaps/AUROC/AP do not depend on the positive training variance scale.
    stat=metrics(v,q[indices]<.7,sessions[indices])[0];base=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')[:,:,0,0];noise=[]
    for j in [1,2]:
        keep=(base[j,indices]<.7)|(base[j,indices]>.9);noise.append(dict(seed_index=j,metrics=metric_dict(metrics(v[keep],base[j,indices[keep]]<.7,sessions[indices[keep]])[0])))
    result=dict(status='COMPLETE',time=stamp(),id=fit['id'],cell=fit['cell'],fit_sha256=fit['sha256'],exploration_spec=fit['spec'],cases=len(indices),metrics=metric_dict(stat),secondary_seeds=noise,
        prospective_family_correction='Holm across all frozen block representatives; pooled after all blocks are frozen',test_accessed=False,validation_used_for_fit=False)
    atomic(path,result);return result
