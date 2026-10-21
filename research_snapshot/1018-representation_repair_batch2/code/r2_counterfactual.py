"""Privileged bounded corrections through the frozen denoising chain, truly rescored."""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def metadata():
    source=read(ROOT/'manifests/data_source.json')
    return read(source['rows'])


def edited_value(engine, block, group, delta, cap):
    import torch
    h = engine.prefix[block]
    mask, valid = engine.mask(block, group)
    if not valid: raise ValueError('Missing token group')
    flat = h.reshape(-1, h.shape[-1]); selected = flat[mask].float()
    limit = float(cap) * selected.norm()
    shift = delta * torch.clamp(limit / (delta.norm().clamp(min=1e-12) * len(selected)**.5), max=1.)
    for _ in range(3):
        trial = (selected + shift).to(h.dtype)
        actual = (trial.float()-selected).norm()
        shift = shift * torch.clamp(limit/actual.detach().clamp(min=1e-12)*.999, max=1.)
    trial = (selected + shift).to(h.dtype)
    actual = (trial.float()-selected).norm()
    trial = torch.where(actual.detach() <= limit+1e-7, trial, flat[mask])
    out = flat.clone(); out[mask] = trial
    metrics = dict(relative_edit=float((trial.float()-selected).norm().detach()/selected.norm()),
                   actual_delta_mean=(trial.float()-selected).mean(0).detach())
    return out.reshape_as(h), metrics


def predict_gradient(engine, features, hidden, interface, value):
    import torch
    from common import reseed
    handle = None
    if interface is not None:
        handle = engine.agent.action_head.feature_encoder.register_forward_hook(lambda m,a,out: interface)
    try:
        batch = {k:v.unsqueeze(0).cuda().float() for k,v in features.items()
                 if k not in ['pixel_values','last_hidden_state']}
        batch['last_hidden_state'] = hidden
        reseed(value)
        with torch.autocast('cuda',enabled=False):
            return engine.agent.forward(batch)['pred_traj'].squeeze(0)
    finally:
        if handle is not None: handle.remove()


def run(engine, task, pool):
    import torch
    import numpy as np
    from vlm_core import raw_features
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    rows = metadata()
    output = []
    block = task['block']; group = task['group']; cap = task['cap']; steps = task['steps']
    for index in task['indices']:
        row = rows[index]; assert row['subset']=='exploration'
        began = time.monotonic(); features = raw_features(row)
        _, target, _ = load_features(row, engine.cfg); target = target.cuda().float()
        with torch.no_grad():
            hidden = engine.forward_native(features)
            native = engine.trajectory(features, hidden, seed(row['token']))
        reference = baseline_row(row)
        assert np.array_equal(native.cpu().numpy(), reference['trajectory'])
        h=engine.prefix[block]; mask,valid=engine.mask(block,group); assert valid
        selected=h.reshape(-1,h.shape[-1])[mask].float()
        radius=float(cap)*selected.norm().item()/len(selected)**.5
        delta=torch.nn.Parameter(torch.zeros(h.shape[-1],device='cuda'))
        optimizer=torch.optim.Adam([delta],lr=max(radius/h.shape[-1]**.5*.25,1e-6))
        records=[]; parameters=[]; gradients=[]
        for iteration in range(steps+1):
            optimizer.zero_grad(set_to_none=True)
            changed,metrics=edited_value(engine,block,group,delta,cap)
            condition,interface=engine.suffix(block,changed)
            prediction=predict_gradient(engine,features,condition,interface,seed(row['token']))
            if iteration==0:
                assert torch.equal(prediction.detach(),native),'Gradient entry is not the native sampler'
            scales=prediction.new_tensor([40.,10.])
            loss=torch.nn.functional.smooth_l1_loss(prediction[:,:2]/scales,target[:,:2]/scales)
            loss=loss+.1*(1-torch.cos(prediction[:,2]-target[:,2])).mean()
            assert torch.isfinite(loss)
            if iteration==0 or iteration==steps or iteration%4==0:
                records.append(dict(arm=f'iteration_{iteration}',iteration=iteration,
                       trajectory=prediction.detach().cpu().numpy().tolist(),surrogate_loss=float(loss.detach()),
                       relative_edit=metrics['relative_edit']))
                parameters.append(delta.detach().cpu().numpy().copy())
            if iteration<steps:
                loss.backward()
                assert delta.grad is not None and torch.isfinite(delta.grad).all()
                gradients.append(float(delta.grad.norm()))
                optimizer.step()
                with torch.no_grad(): delta.mul_(torch.clamp(delta.new_tensor(radius)/delta.norm().clamp(min=1e-12),max=1.))
        records.append(dict(arm='GT_reference',trajectory=target.cpu().numpy().tolist()))
        scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],
                         scoring=engine.cfg['scoring'],records=records)).result(timeout=1800)
        assert scored[0]['score']==reference['score']
        chosen=max(range(len(parameters)),key=lambda i:scored[i]['score']['score'])
        selected_delta=torch.tensor(parameters[chosen],device='cuda')
        transfer=[]
        with torch.no_grad():
            changed,metrics=edited_value(engine,block,group,selected_delta,cap)
            condition,interface=engine.suffix(block,changed)
            for j in task.get('transfer_seeds',[1,2]):
                baseline=engine.trajectory(features,hidden,seed(row['token'],j))
                prediction=engine.trajectory(features,condition,seed(row['token'],j),interface)
                transfer.extend([dict(arm='baseline',seed_index=j,trajectory=baseline.cpu().numpy().tolist()),
                                 dict(arm='selected_on_S0',seed_index=j,trajectory=prediction.cpu().numpy().tolist())])
        transferred=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],
                               scoring=engine.cfg['scoring'],records=transfer)).result(timeout=1800) if transfer else []
        ident=f'{task["id"]}_{index:06d}'
        destination=ROOT/'analysis/case_corrections'/ident
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.with_suffix('.npz').open('wb') as stream:
            np.savez(stream,delta=np.asarray(parameters[chosen]),actual_delta_mean=metrics['actual_delta_mean'].cpu().numpy(),
                     candidates=np.asarray(parameters),global_index=index)
        value=dict(status='COMPLETE',time=stamp(),token=row['token'],global_index=index,session=row['session'],
                   block=block,group=group,cap=cap,steps=steps,records=scored,selected_index=chosen,
                   selected_on='actual S0 PDMS, Base included',transfer=transferred,
                   gradient_norms=gradients,seconds=time.monotonic()-began,
                   proxy='GT normalized XY smooth-L1 plus heading cosine; PDMS is not differentiated',
                   privileged=True,deployable=False,arrays=str(destination.with_suffix('.npz').relative_to(ROOT)),
                   arrays_sha256=sha(destination.with_suffix('.npz')))
        atomic(destination.with_suffix('.json'),value)
        output.append(dict(token=row['token'],path=str(destination.with_suffix('.json').relative_to(ROOT)),
                           base=reference['score']['score'],best=scored[chosen]['score']['score']))
        engine.verify_engine()
    return dict(records=output,handler_sha256=task['handler_sha256'])
