"""Matched-budget privileged channel-subspace optimization, actually rescored.

Same loss, sampler, cap and score checkpoints as the original per-case optimizer.
A smaller coefficient space uses radius/sqrt(rank) learning rate, matching the
first Adam step's channel-norm scale; equal steps are not a theoretical optimum.
"""
from r2_common import *


def run(engine,task,pool):
    import torch
    import numpy as np
    from worker import load_features
    from r2_cached_interfaces import from_cached
    from r2_counterfactual import edited_value,predict_gradient
    from repair_engine import baseline_row
    from repair_score import score_group
    from r2_expert_space import save_npz
    rows=read(read(ROOT/'manifests/data_source.json')['rows']);output=[];block=task['block'];cap=task['cap'];steps=task['steps'];basis=None
    if task['space']!='full':
        assert sha(ROOT/task['basis']['path'])==task['basis']['sha256']
        with np.load(ROOT/task['basis']['path']) as z:b=np.array(z['basis'])[:,:task['rank']]
        assert b.shape[1]==task['rank'] and np.allclose(b.T@b,np.eye(b.shape[1]),atol=1e-4);basis=torch.as_tensor(b,device='cuda',dtype=torch.float32)
    for index in task['indices']:
        began=time.monotonic();row=rows[index];assert row['subset']=='exploration';assert int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5==task['diagnostic_fold'];features,target,_=load_features(row,engine.cfg);target=target.cuda().float()
        with torch.no_grad():hidden=from_cached(engine,features,index);native=engine.trajectory(features,hidden,seed(row['token']))
        reference=baseline_row(row);assert np.array_equal(native.cpu().numpy(),reference['trajectory']);h=engine.prefix[block];mask,valid=engine.mask(block,'valid_mean');assert valid;selected=h.reshape(-1,h.shape[-1])[mask].float();radius=float(cap)*selected.norm().item()/len(selected)**.5;r=h.shape[-1] if basis is None else basis.shape[1]
        coefficient=torch.nn.Parameter(torch.zeros(r,device='cuda'));optimizer=torch.optim.Adam([coefficient],lr=max(radius/r**.5*.25,1e-6));records=[];parameters=[];gradients=[]
        for iteration in range(steps+1):
            optimizer.zero_grad(set_to_none=True);delta=coefficient if basis is None else basis@coefficient;changed,stat=edited_value(engine,block,'valid_mean',delta,cap);condition,post=engine.suffix(block,changed);prediction=predict_gradient(engine,features,condition,post,seed(row['token']))
            if iteration==0:assert torch.equal(prediction.detach(),native)
            scales=prediction.new_tensor([40.,10.]);loss=torch.nn.functional.smooth_l1_loss(prediction[:,:2]/scales,target[:,:2]/scales)+.1*(1-torch.cos(prediction[:,2]-target[:,2])).mean();assert torch.isfinite(loss)
            if iteration==0 or iteration==steps or iteration%4==0:
                records.append(dict(arm='iteration_'+str(iteration),iteration=iteration,trajectory=prediction.detach().cpu().numpy().tolist(),surrogate_loss=float(loss.detach()),relative_edit=stat['relative_edit']));parameters.append(delta.detach().cpu().numpy().copy())
            if iteration<steps:
                loss.backward();assert coefficient.grad is not None and torch.isfinite(coefficient.grad).all();gradients.append(float(coefficient.grad.norm()));optimizer.step()
                with torch.no_grad():coefficient.mul_(torch.clamp(coefficient.new_tensor(radius)/coefficient.norm().clamp(min=1e-12),max=1.))
        records.append(dict(arm='GT_reference',trajectory=target.cpu().numpy().tolist()));scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=1800);assert scored[0]['score']==reference['score'];chosen=max(range(len(parameters)),key=lambda j:scored[j]['score']['score']);delta=torch.as_tensor(parameters[chosen],device='cuda');transfer=[]
        with torch.no_grad():
            changed,stat=edited_value(engine,block,'valid_mean',delta,cap);condition,post=engine.suffix(block,changed)
            for noise in [1,2]:
                native_noise=engine.trajectory(features,hidden,seed(row['token'],noise));after=engine.trajectory(features,condition,seed(row['token'],noise),post)
                transfer.extend([dict(arm='baseline',seed_index=noise,trajectory=native_noise.cpu().numpy().tolist()),dict(arm='selected_on_S0',seed_index=noise,trajectory=after.cpu().numpy().tolist())])
        transferred=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=transfer)).result(timeout=1800);path=ROOT/'analysis/space_controllability'/task['id']/str(index);hashed=save_npz(path.with_suffix('.npz'),candidates=np.asarray(parameters),delta=np.asarray(parameters[chosen]),global_index=index)
        if task.get('reference_compare'):
            old=read(ROOT/task['reference_compare']);assert old['global_index']==index and old['block']==block and old['cap']==cap and old['steps']==steps
            assert old['records']==scored and old['transfer']==transferred,'Cached/full optimizer must reproduce original real trajectories and scores exactly'
            with np.load(ROOT/old['arrays']) as z:assert np.array_equal(z['candidates'],np.asarray(parameters))
        record=dict(status='COMPLETE',time=stamp(),task=task,index=index,token=row['token'],session=row['session'],records=scored,selected_index=chosen,transfer=transferred,gradient_norms=gradients,seconds=time.monotonic()-began,arrays=str(path.with_suffix('.npz').relative_to(ROOT)),arrays_sha256=hashed,
            actual_rank=r,shared_shift_across_valid_tokens=True,privileged=True,deployable=False,GT_and_real_S0_selection_used=True,new_observations=False,reference_exact=bool(task.get('reference_compare')));atomic(path.with_suffix('.json'),record);output.append(dict(path=str(path.with_suffix('.json').relative_to(ROOT)),base=scored[0]['score']['score'],best=scored[chosen]['score']['score']))
        engine.verify_engine()
    return dict(records=output)
