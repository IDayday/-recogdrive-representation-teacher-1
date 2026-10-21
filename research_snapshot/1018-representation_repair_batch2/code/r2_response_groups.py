"""One bounded assignment update from actual outcomes, preserving unresolved cases.

This is training-only EM evidence. Held-fold samples cannot influence assignment,
group geometry, or refitted experts. No equal-size load balancing is imposed.
"""
from r2_common import *


def run(task):
    import numpy as np
    from scipy.special import softmax
    from r2_expert_space import save_npz
    selection=read(ROOT/task['selection']);held=selection['heldout_fold'];K=selection['K']
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows'])
    parent=selection['arms'][0]['training_task']['responsibility_meta'];meta=read(ROOT/parent)
    with np.load(ROOT/meta['path']) as z:indices=np.array(z['global_indices']);prior=np.array(z['responsibility'],dtype=np.float64)
    assert prior.shape==(len(indices),K)
    for i in indices:assert rows[i]['subset']=='exploration' and (held<0 or int(digest(dict(session=rows[i]['session'],cv_root=20261016))[:8],16)%5!=held)
    mapping={int(i):j for j,i in enumerate(indices)};gain=np.zeros((len(indices),K));counts=np.zeros_like(gain);risk=np.zeros_like(gain)
    source_hashes=[]
    for response_path in task['responses']:
        response=read(ROOT/response_path);point=read(ROOT/response['point']);assert point['heldout_fold']==held
        with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);score=np.array(z['scores'])
        by_slot={}
        for part in selection['arms']:by_slot.setdefault(part['slot'],[]).append(ids.index(part['id']))
        for j,index in enumerate(ii):
            if int(index) not in mapping:continue
            pos=mapping[int(index)];base=score[j,0]
            for slot,arms in by_slot.items():
                after=score[j,arms];delta=after[:,:,0]-base[None,:,0]
                damage=(after[:,:,1]<base[None,:,1]).astype(float)+(after[:,:,2]<base[None,:,2]).astype(float)+((after[:,:,0]==0)&(base[None,:,0]>0)).astype(float)
                utility=delta-task.get('risk_weight',.25)*damage
                best=np.argmax(utility,axis=0);chosen=utility[best,np.arange(utility.shape[1])]
                gain[pos,slot]+=chosen.sum();risk[pos,slot]+=damage[best,np.arange(utility.shape[1])].sum();counts[pos,slot]+=len(chosen)
        source_hashes.append(dict(path=response_path,matrix_sha256=response['matrix_sha256'] if 'matrix_sha256' in response else sha(ROOT/response['matrix'])))
    mean=np.divide(gain,counts,out=np.zeros_like(gain),where=counts>0)
    active=np.any(counts>0,axis=0);unresolved=np.max(mean,axis=1)<=.005
    # Missing measurements remain missing; they are never interpreted as zero
    # gain in the assignment softmax. Existing membership remains for unresolved.
    logits=mean/task.get('temperature',.05)+.2*np.log(np.maximum(prior,1e-12));logits[counts==0]=-1e6
    q=.8*softmax(logits,axis=1)+.2*prior;q[unresolved]=prior[unresolved];q/=q.sum(1,keepdims=True)
    hard=q.argmax(1);ess=q.sum(0)**2/np.maximum(np.square(q).sum(0),1e-12)
    sessions=[len({rows[i]['session'] for i in indices[hard==e]}) for e in range(K)]
    ident=selection['system']+'_em1';folder=ROOT/'analysis/response_refinement'/('all' if held<0 else f'fold{held}')
    path=folder/(ident+'.npz');hashed=save_npz(path,global_indices=indices,responsibility=q.astype('float32'),parent_responsibility=prior.astype('float32'),actual_utility=mean.astype('float32'),observations=counts.astype('int16'),unresolved=unresolved)
    positive=mean>.01;overlap=(positive.T@positive.astype(float))/(np.maximum(positive.sum(0)[:,None]+positive.sum(0)[None,:]-(positive.T@positive.astype(float)),1))
    stats=dict(status='PASS',time=stamp(),id=ident,parent_system=selection['system'],K=K,heldout_fold=held,fit_seed=meta['fit_seed'],
        path=str(path.relative_to(ROOT)),sha256=hashed,parent_responsibility_meta=parent,effective_counts=ess.tolist(),sessions=sessions,hard_counts=np.bincount(hard,minlength=K).tolist(),
        changed_hard_fraction=float(np.mean(hard!=prior.argmax(1))),unresolved_cases=int(unresolved.sum()),unresolved_preserved=True,
        actual_response_counts=dict(minimum=int(counts.min()),maximum=int(counts.max()),cross_noise_cases=int(np.sum(counts.max(1)>1))),
        active_response_slots=np.flatnonzero(active).tolist(),positive_repair_jaccard=overlap.tolist(),
        gain_nonlinearity='Uses actual separately generated candidates. This is assignment evidence, not a mixed-policy prediction.',
        training_only=True,outer_heldfold_excluded=True,response_sources=source_hashes,task=task,
        no_validation_or_test_fitted=True,no_forced_load_balance=True)
    atomic(path.with_suffix('.json'),stats);return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),changed_fraction=stats['changed_hard_fraction'],unresolved=stats['unresolved_cases'])
