"""Train/load the uniform-token control, verify mean-only access and true scoring."""
from r2_common import *


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_uniform_critic_train import run as train
    from r2_token_critic import load
    from r2_library_rollouts import load as case
    from r2_cached_interfaces import from_cached
    from r2_token_critic_eval import run as evaluate
    from repair_engine import baseline_row
    assert read(ROOT/'provenance/TOKEN_PREFETCH_AB_PASS.json')['all_arrays_bitwise_equal']
    spec=dict(read(ROOT/'runs/token_critic_pilot_v1/tasks.json')[0],id='uniform_token_critic_pilot_v1')
    result=train(engine,spec,pool);trained=read(ROOT/result['path']);checkpoint=trained['checkpoints'][-1]
    with np.load(ROOT/checkpoint['path']) as z:
        assert all(np.count_nonzero(z[f'attention.{i}.in_proj_weight'][:256])==0 and np.count_nonzero(z[f'attention.{i}.in_proj_bias'][:256])==0 for i in range(2))
    model=load(checkpoint['path'],checkpoint['sha256']);maximum=0.;panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel']
    with torch.no_grad():
        for index in panel:
            row,features,reference=case(index,engine.cfg,True);from_cached(engine,features,index);h=engine.prefix['interface_post'];mask,valid=engine.mask('interface_post','valid_mean');assert valid
            context=h.reshape(-1,h.shape[-1])[mask];trajectory=torch.as_tensor(np.asarray(reference['trajectory'],dtype=np.float32),device='cuda')[None]
            full=model(context,trajectory);mean=model(context.mean(0,keepdim=True),trajectory);error=float((full-mean).abs().max());assert error<1e-5;maximum=max(maximum,error)
    old_point=read(ROOT/'runs/token_critic_engineering_v1/points/smoke.json');point_path=ROOT/task['stage']/'points/evaluation.json'
    point=dict(old_point,id='uniform_token_critic_smoke',critics=[dict(id='uniform_critic',checkpoint=checkpoint,heldout_fold=-1,threshold=.01,risk_penalty=0.),dict(id='uniform_identity',checkpoint=checkpoint,heldout_fold=-1,threshold=2.,risk_penalty=0.,force_Base=True)])
    atomic(point_path,point);actual=evaluate(engine,dict(task,id=task['id']+'_actual',point=str(point_path.relative_to(ROOT)),start=0,end=len(panel)),pool)
    path=ROOT/'provenance/UNIFORM_TOKEN_CRITIC_ENGINEERING_PASS.json';atomic(path,dict(status='PASS',time=stamp(),trained_checkpoint=checkpoint,
        QK_remain_exactly_zero=True,existing_full_model_loader_compatible=True,maximum_full_vs_mean_difference=maximum,
        same_training_data_schedule_loss_architecture=True,actual_candidate_scoring=actual['path'],
        comparison_scope='Only conditional token weighting removed; same initial remaining weights and actual data. Not a proof of information absence.'))
    return dict(path=str(path.relative_to(ROOT)),maximum_full_vs_mean_difference=maximum)
