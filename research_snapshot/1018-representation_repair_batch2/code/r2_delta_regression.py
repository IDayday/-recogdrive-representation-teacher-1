"""Experts learn their own causal output spaces from effective case corrections.

Targets are privileged during training. Inference uses only current pooled hidden
state. Quality-difference bases and this outcome-derived basis are distinct arms.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=4)
def teacher_data(block,cap):
    import numpy as np
    rows=read(read(ROOT/'manifests/data_source.json')['rows'])
    which=[.005,.02,.1].index(cap);files=sorted((ROOT/'analysis/case_corrections').glob(f'correction_{block}_c{which}_*.json'))
    assert len(files)==1850
    indices=[];values=[];gains=[];safe=[]
    for path in files:
        d=read(path);indices.append(d['global_index'])
        with np.load(ROOT/d['arrays']) as z:values.append(np.array(z['actual_delta_mean'],dtype=np.float64))
        a=d['records'][0]['score'];b=d['records'][d['selected_index']]['score']
        gains.append(b['score']-a['score'])
        safe.append(b['no_at_fault_collisions']>=a['no_at_fault_collisions'] and b['drivable_area_compliance']>=a['drivable_area_compliance'] and not(b['score']==0 and a['score']>0))
    order=np.argsort(indices)
    return rows,np.asarray(indices)[order],np.asarray(values)[order],np.asarray(gains)[order],np.asarray(safe)[order]


def run(task):
    import numpy as np
    from scipy.linalg import svd,solve
    from sklearn.utils.extmath import randomized_svd
    from r2_expert_space import save_npz
    rows,all_indices,all_target,all_gain,safe=teacher_data(task['block'],task['cap'])
    held=task.get('heldout_fold',-1);meta=read(ROOT/task['responsibility_meta']);assert meta['heldout_fold']==held
    with np.load(ROOT/meta['path']) as z:
        failure=np.array(z['global_indices']);membership=np.array(z['responsibility'][:,task['expert']],dtype=np.float64)
    mapping={int(i):j for j,i in enumerate(all_indices)};positions=np.array([mapping[int(i)] for i in failure])
    target=all_target[positions].copy();gains=all_gain[positions]
    if task.get('safety_targets',False):target[~safe[positions]]=0
    assert len(failure)>=24
    ess=float(membership.sum()**2/(membership@membership));assert ess>=24
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    assert np.all(train[failure])
    cell=next(c for c in read(ROOT/'manifests/cells.json') if c['cell']==task['block']+'__valid_mean')
    x=np.load(cell['absolute_path'],mmap_mode='r')
    high=np.array([i for i,r in enumerate(rows) if train[i] and r['quality']>.9])
    high=np.array(sorted(high,key=lambda i:digest(dict(token=rows[i]['token'],delta_retention=20261018)))[:1024])
    mid=np.array([i for i,r in enumerate(rows) if train[i] and .7<=r['quality']<=.9])
    mid=np.array(sorted(mid,key=lambda i:digest(dict(token=rows[i]['token'],delta_retention=20261018)))[:256])
    cases=np.concatenate([failure,high,mid]);raw=np.asarray(x[cases],dtype=np.float64)
    mean=np.asarray(x[high],dtype=np.float64).mean(0);scale=np.asarray(x[high],dtype=np.float64).std(0)
    scale=np.maximum(scale,max(float(np.median(scale))*1e-3,1e-6))
    normalized=np.clip((raw-mean)/scale,-20,20)
    weights=np.concatenate([membership,np.full(len(high),membership.sum()*task.get('retention_weight',2.)/len(high)),np.full(len(mid),membership.sum()*.5/max(len(mid),1))])
    weights=weights/weights.sum()
    max_input=min(max(task['input_ranks']),min(normalized.shape)-1)
    _,_,vt=randomized_svd(normalized*np.sqrt(weights)[:,None],n_components=max_input,random_state=task['fit_seed'])
    _,singular,output_v=svd(target*np.sqrt(membership/membership.sum())[:,None],full_matrices=False,check_finite=False)
    output_rank=int(np.count_nonzero(singular>max(float(singular[0])*1e-5,1e-10))) if len(singular) else 0
    if not output_rank:
        result=dict(status='NO_EFFECTIVE_TEACHER_DIRECTION',time=stamp(),task=task,failures=len(failure),effective_cases=ess)
        path=ROOT/'analysis/delta_experts'/(task['id']+'.json');atomic(path,result);return dict(path=str(path.relative_to(ROOT)),fits=0)
    y=np.concatenate([target,np.zeros((len(high)+len(mid),target.shape[1]))])
    fits=[]
    for ri in task['input_ranks']:
        if ri>max_input:continue
        bi=vt[:ri].T;design=np.column_stack([normalized@bi,np.ones(len(cases))])
        gram=(design*weights[:,None]).T@design;penalty=max(float(np.trace(gram[:-1,:-1])/ri),1e-8)
        for ro in task['output_ranks']:
            if ro>output_rank:continue
            bo=output_v[:ro].T;rhs=(design*weights[:,None]).T@(y@bo)
            for lam in task['ridge']:
                regular=gram+float(lam)*penalty*np.diag(np.r_[np.ones(ri),0.])
                coef=solve(regular+np.eye(ri+1)*1e-10,rhs,assume_a='pos',check_finite=False)
                prediction=(design@coef)@bo.T
                err=float(np.sum(weights[:,None]*(prediction-y)**2))
                norm=float(np.sum(weights[:,None]*y**2))
                spec=dict(task=task['id'],input_rank=ri,output_rank=ro,ridge=lam)
                ident='delta_'+digest(spec)[:24];path=ROOT/'delta_experts'/ident[:8]/(ident+'.npz')
                hashed=save_npz(path,**{k:v.astype('float32') for k,v in dict(input_mean=mean,input_scale=scale,input_basis=bi,output_basis=bo,coef=coef).items()})
                record=dict(status='FIT_NOT_BEHAVIOR_EVALUATED',time=stamp(),id=ident,path=str(path.relative_to(ROOT)),sha256=hashed,
                       block=task['block'],group='valid_mean',cap=task['cap'],input_rank=ri,output_rank=ro,ridge=lam,
                       fit_seed=task['fit_seed'],heldout_fold=held,system=meta['id'],K=meta['K'],expert=task['expert'],
                       responsibility_meta=task['responsibility_meta'],source=task['id'],target='Actually effective per-case hidden delta; zero retention targets',
                       normalized_training_error=err/max(norm,1e-20),causal_output_space_rank=output_rank,
                       teacher_improved_cases=int(np.count_nonzero(gains>1e-8)),effective_cases=ess,
                       retained_successes=len(high),retained_intermediate=len(mid),safety_targets=task.get('safety_targets',False),
                       deployment_uses_GT_or_PDMS=False)
                atomic(path.with_suffix('.json'),record);fits.append(record)
    result=dict(status='COMPLETE',time=stamp(),task=task,fits=fits,causal_rank=output_rank,
                cumulative_delta_energy=(np.cumsum(singular**2)/max(float(np.sum(singular**2)),1e-20)).tolist(),
                effective_failure_cases=ess,training_failure_cases=len(failure),validation_fitted=False,test_accessed=False,
                behavior_must_be_tested=True)
    path=ROOT/'analysis/delta_experts'/(task['id']+'.json');atomic(path,result)
    return dict(path=str(path.relative_to(ROOT)),fits=len(fits),causal_rank=output_rank)


@lru_cache(maxsize=128)
def load(path,expected_hash):
    import torch
    import numpy as np
    assert sha(ROOT/path)==expected_hash
    with np.load(ROOT/path) as z:return {k:torch.tensor(np.array(z[k]),device='cuda',dtype=torch.float32) for k in z.files}


def apply(engine,fit,strength=1.):
    import torch
    from r2_counterfactual import edited_value
    a=load(fit['path'],fit['sha256']);h=engine.prefix[fit['block']];mask,valid=engine.mask(fit['block'],'valid_mean')
    if not valid:return h,dict(relative_edit=0.)
    pooled=h.reshape(-1,h.shape[-1])[mask].float().mean(0)
    state=torch.clamp((pooled-a['input_mean'])/a['input_scale'],-20,20)@a['input_basis']
    state=torch.cat([state,state.new_ones(1)]);delta=a['output_basis']@(state@a['coef'])*strength
    return edited_value(engine,fit['block'],'valid_mean',delta,fit['cap']*strength)
