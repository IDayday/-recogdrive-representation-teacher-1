"""Real raw multi-location gradient, identity, training and scoring acceptance."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_library_rollouts import load,block
    from r2_eval_rollouts import Fits
    from r2_mixed_locations_v3 import forward
    from r2_counterfactual import predict_gradient
    from r2_behavior_router_raw_locations_v1 import run as train
    from r2_behavior_router_raw_eval_v1 import run as evaluate
    parts=task['parts'];assert len(parts)==3
    assert any(block(p).startswith('vision') for p in parts)
    assert any(block(p).startswith('language') for p in parts)
    assert any(block(p).startswith('interface') for p in parts)
    fits=Fits();checks=[]
    for index in task['panel']:
        row,features,reference=load(index,engine.cfg,False)
        with torch.no_grad():
            hidden=engine.forward_native(features);native=engine.trajectory(features,hidden,seed(row['token']))
            assert np.array_equal(native.cpu().numpy(),reference['trajectory'])
            zero=hidden.new_tensor([1.,0.,0.,0.]);amount=hidden.new_ones(3)
            condition,post,statistics=forward(engine,parts,zero,amount,fits)
            assert torch.equal(condition,hidden),'Raw identity changed the native prefix'
            result=engine.trajectory(features,condition,seed(row['token']),post)
            assert torch.equal(result,native),'Raw identity changed the native trajectory'
        weights=torch.nn.Parameter(hidden.new_tensor([.1,.3,.3,.3]))
        condition,post,statistics=forward(engine,parts,weights,amount,fits)
        prediction=predict_gradient(engine,features,condition,post,seed(row['token']))
        loss=(prediction[:,:2]/prediction.new_tensor([40.,10.])).square().mean();loss.backward()
        assert weights.grad is not None and torch.isfinite(weights.grad).all() and weights.grad[1:].abs().max()>1e-10
        values=torch.stack(statistics).detach().cpu().numpy();assert np.all(values[:,0]<=values[:,2]+1e-6)
        checks.append(dict(index=index,zero_prefix_and_trajectory_exact=True,gradient=weights.grad.detach().cpu().numpy().tolist(),site_statistics=values.tolist()))
        engine.verify_engine()
    models=[]
    for kind in ['hard_continuous','soft_joint']:
        spec=dict(id=task['id']+'_'+kind,selection=task['selection'],responses=[],role='PDMS',tier='denoising',kind=kind,
                  fit_seed=2026101801,steps=8,checkpoints=[8],warmup_steps=0)
        result=train(engine,spec,pool);models.append(read(ROOT/result['path']))
    policies=[]
    for model in models:
        for force in [False,True]:policies.append(dict(id=model['kind']+('_zero' if force else ''),model=model,checkpoint=model['checkpoints'][-1],force_Base=force,identity_threshold=1.01))
    point=ROOT/task['stage']/'points/actual_eval.json'
    atomic(point,dict(id=task['id'],mode='engineering',policies=policies,panel=task['panel'],seeds=[0,1,2]))
    actual=evaluate(engine,dict(id=task['id']+'_actual',stage=task['stage'],point=str(point.relative_to(ROOT)),start=0,end=len(task['panel'])),pool)
    path=ROOT/'provenance/RAW_MULTISITE_ROUTER_ENGINEERING_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),checks=checks,parts=parts,training_paths=[str((ROOT/'behavior_routers'/m['task']['id']/'TRAINING.json').relative_to(ROOT)) for m in models],
        actual_generated_and_scored=actual,base_frozen=True,hard_and_true_soft=True,
        interpretation='Engineering-only mixed vision/language/interface toy bank, not a selected scientific expert system and not evidence of generalization.'))
    return dict(path=str(path.relative_to(ROOT)),actual=actual)
