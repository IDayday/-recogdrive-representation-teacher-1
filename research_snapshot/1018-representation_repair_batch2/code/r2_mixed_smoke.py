"""Verify exact identity, multi-site mixture gradients and independent scoring."""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    import torch
    from r2_eval_rollouts import Fits,load_case
    from r2_mixed_interventions import mixed_forward
    from r2_counterfactual import predict_gradient
    from r2_learned_expert import training_loss
    from repair_score import score_group
    from worker import load_features
    descriptor=read(ROOT/task['point']);fits=Fits();output=[]
    for index in descriptor['panel']:
        row,features,reference,_=load_case(index)
        with torch.no_grad():
            hidden=engine.forward_native(features)
            native=engine.trajectory(features,hidden,seed(row['token']))
            zero_hidden,zero_interface,zero_stats=mixed_forward(engine,descriptor['parts'],[1.,0.,0.,0.],fits)
            zero=engine.trajectory(features,zero_hidden,seed(row['token']),zero_interface)
        assert torch.equal(native,zero),'Zero expert must reproduce the native trajectory exactly'
        _,target,_=load_features(row,engine.cfg);target=target.cuda().float()
        logits=torch.tensor([0.,-.2,.1,-.4],device='cuda',requires_grad=True)
        weights=torch.softmax(logits,0)
        soft_hidden,soft_interface,stats=mixed_forward(engine,descriptor['parts'],weights,fits)
        prediction=predict_gradient(engine,features,soft_hidden,soft_interface,seed(row['token']))
        loss=training_loss(prediction,target);loss.backward()
        assert logits.grad is not None and torch.isfinite(logits.grad).all() and logits.grad.norm()>0
        statistics=torch.stack(stats).detach().cpu().numpy()
        assert np.all(statistics[:,0]<=statistics[:,2]+1e-6)
        records=[dict(arm='baseline',trajectory=native.cpu().numpy().tolist()),
                 dict(arm='identity_mixture',trajectory=zero.cpu().numpy().tolist()),
                 dict(arm='joint_soft_mixture',trajectory=prediction.detach().cpu().numpy().tolist())]
        scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=1800)
        assert scored[0]['score']==reference['score'] and scored[1]['score']==reference['score']
        output.append(dict(token=row['token'],weights=weights.detach().cpu().tolist(),gradient=logits.grad.cpu().tolist(),
                           loss=float(loss.detach()),statistics=statistics.tolist(),records=scored))
        engine.verify_engine()
    path=ROOT/'provenance/MIXED_INTERVENTION_SMOKE_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),task=task,exact_identity=True,real_downstream_gradient=True,
                     base_frozen=True,real_scoring=True,multi_site=True,same_site_parallel_deltas=True,cases=output))
    return dict(path=str(path.relative_to(ROOT)),cases=len(output))
