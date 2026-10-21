"""Raw/cache equality for masks, states, seeds, gradients and true scores."""
from r2_common import *


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_eval_rollouts import load_case
    from worker import load_features
    from r2_cached_interfaces import from_cached
    from r2_counterfactual import edited_value,predict_gradient
    from r2_learned_expert import training_loss
    from repair_score import score_group
    checks=[]
    for index in task['indices']:
        row,raw,reference,_=load_case(index);cached,target,_=load_features(row,engine.cfg);target=target.cuda()
        for key in ['history_trajectory','status_feature','high_command_one_hot']:assert torch.equal(raw[key],cached[key])
        with torch.no_grad():
            native=engine.forward_native(raw);ids=engine.inputs['input_ids'].clone();attention=engine.inputs['attention_mask'].clone()
            original={b:engine.prefix[b].clone() for b in ['interface_pre','interface_post']};mask=engine.lm[0].clone()
            predictions=[engine.trajectory(raw,native,seed(row['token'],j)) for j in [0,1,2]]
            restored=from_cached(engine,cached,index)
            assert torch.equal(native,restored) and torch.equal(ids,engine.inputs['input_ids'])
            assert torch.equal(attention,engine.inputs['attention_mask']) and torch.equal(mask,engine.lm[0])
            for block in original:assert torch.equal(original[block],engine.prefix[block])
            for j,p in enumerate(predictions):assert torch.equal(p,engine.trajectory(cached,restored,seed(row['token'],j)))
        details=[]
        for block in ['interface_pre','interface_post']:
            outputs=[];gradients=[]
            for use_cache in [False,True]:
                with torch.no_grad():
                    h=from_cached(engine,cached,index) if use_cache else engine.forward_native(raw)
                delta=torch.linspace(-.01,.01,h.shape[-1] if block=='interface_pre' else engine.prefix[block].shape[-1],device='cuda',requires_grad=True)
                changed,metrics=edited_value(engine,block,'valid_mean',delta,.02)
                condition,post=engine.suffix(block,changed)
                prediction=predict_gradient(engine,cached if use_cache else raw,condition,post,seed(row['token'],1))
                loss=training_loss(prediction,target);loss.backward()
                outputs.append(prediction.detach());gradients.append(delta.grad.detach())
            assert torch.equal(outputs[0],outputs[1]) and torch.equal(gradients[0],gradients[1])
            scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=[
                dict(arm='raw',trajectory=outputs[0].cpu().numpy().tolist()),dict(arm='cached',trajectory=outputs[1].cpu().numpy().tolist())])).result(timeout=1800)
            assert scored[0]['score']==scored[1]['score'];details.append(dict(block=block,trajectory_exact=True,gradient_exact=True,score_exact=True))
        engine.verify_engine();checks.append(dict(token=row['token'],input_ids_exact=True,actual_padding_mask_exact=True,states_exact=True,S0_S1_S2_native_exact=True,interventions=details))
    path=ROOT/'provenance/CACHED_INTERFACE_SMOKE_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),checks=checks,raw_VLM_weights_unchanged=True,cached_scope='interface_pre/post only'))
    return dict(path=str(path.relative_to(ROOT)),cases=len(checks))
