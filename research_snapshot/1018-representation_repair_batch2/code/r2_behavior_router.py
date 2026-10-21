"""Train hard+continuous or truly joint soft repair on final sampled behavior.

Experts and Base are frozen. Soft weights include identity without renormalizing
it away; hard uses a straight-through categorical decision and exact zero option.
Deployment features come from current interfaces, optionally current Base output.
No GT or true score enters a deployment decision.
"""
from r2_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


def make_model(dimension,count):
    import torch
    class Router(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.trunk=torch.nn.Sequential(torch.nn.Linear(dimension,128),torch.nn.Tanh(),torch.nn.Linear(128,64),torch.nn.Tanh())
            self.logits=torch.nn.Linear(64,count+1);self.amount=torch.nn.Linear(64,count)
            torch.nn.init.zeros_(self.logits.weight);torch.nn.init.zeros_(self.logits.bias)
            self.logits.bias.data[0]=1.5
            torch.nn.init.zeros_(self.amount.weight);torch.nn.init.zeros_(self.amount.bias)
        def forward(self,x):
            h=self.trunk(x);return self.logits(h),2*torch.sigmoid(self.amount(h))
    return Router().cuda().float()


@lru_cache(maxsize=6)
def representation(held):
    import numpy as np
    from r2_learned_expert import checkpoint_arrays
    fold='all' if held<0 else f'fold{held}';meta=read(ROOT/'router_features'/fold/'COMPLETE.json')
    with np.load(ROOT/meta['path']) as z:
        transforms={k:np.array(z[k]) for k in z.files if k.endswith(('_mean','_scale','_basis','_projection_scale'))}
    return transforms,meta


def current_feature(engine,base,states,held,tier):
    import torch
    from r2_router_features import trajectory_features
    transforms,_=representation(held);pieces=[]
    for site in ['interface_pre','interface_post']:
        view=site+'__valid_mean';h=engine.prefix[site];mask,valid=engine.mask(site,'valid_mean');assert valid
        p=h.reshape(-1,h.shape[-1])[mask].float().mean(0)
        key=(held,site)
        if not hasattr(engine,'behavior_router_transforms'):engine.behavior_router_transforms={}
        if key not in engine.behavior_router_transforms:
            engine.behavior_router_transforms[key]={suffix:torch.as_tensor(transforms[view+suffix],device='cuda') for suffix in ['_mean','_scale','_basis','_projection_scale']}
        a=engine.behavior_router_transforms[key]
        pieces.append((torch.clamp((p-a['_mean'])/a['_scale'],-20,20)@a['_basis'])/a['_projection_scale'])
    if tier in ['trajectory','denoising']:pieces.append(torch.as_tensor(trajectory_features(base.detach().cpu().numpy()),device='cuda'))
    if tier=='denoising':pieces.append(states.detach().reshape(-1))
    return torch.cat(pieces).detach()


def base_trajectory(engine,features,hidden,value,trace=False):
    import torch
    if not trace:return engine.trajectory(features,hidden,value),None
    original=engine.agent.action_head.p_mean_variance;states=[]
    def traced(x,*a,**kw):states.append(x.detach().clone());return original(x,*a,**kw)
    engine.agent.action_head.p_mean_variance=traced
    try:trajectory=engine.trajectory(features,hidden,value)
    finally:engine.agent.action_head.p_mean_variance=original
    assert len(states)==5
    return trajectory,torch.stack(states).squeeze(1)


def coefficients(logits,amount,kind,training=False,temperature=1.):
    import torch
    probability=torch.softmax(logits/temperature,dim=-1)
    if kind=='hard_continuous':
        hard=torch.nn.functional.one_hot(probability.argmax(-1),num_classes=len(logits)).float()
        weights=hard+(probability-probability.detach()) if training else hard
    else:
        assert kind=='soft_joint';weights=probability
    return weights,amount


def run(engine,task,pool):
    import torch
    import numpy as np
    from common import reseed
    from worker import load_features
    from repair_engine import baseline_row
    from r2_cached_interfaces import from_cached
    from r2_eval_rollouts import Fits
    from r2_learned_expert import target_for,training_loss
    from r2_mixed_interfaces_v2 import forward
    from r2_counterfactual import predict_gradient
    from r2_expert_space import save_npz
    selection=read(ROOT/task['selection']);held=selection['heldout_fold'];role=task['role'];kind=task['kind'];tier=task['tier']
    by_id={p['id']:p for p in selection['arms']};ordered=sorted(selection['policies'][role].items(),key=lambda z:int(z[0]));parts=[by_id[v] for _,v in ordered]
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    failure=np.flatnonzero(train&(quality<.7));high=np.flatnonzero(train&(quality>.9));mid=np.flatnonzero(train&(quality>=.7)&(quality<=.9))
    assert len(failure) and len(high) and len(parts)>=1
    dimension=64+(32 if tier in ['trajectory','denoising'] else 0)+(120 if tier=='denoising' else 0)
    reseed(task['fit_seed']);router=make_model(dimension,len(parts));optimizer=torch.optim.AdamW(router.parameters(),lr=.001,weight_decay=.001)
    rng=np.random.default_rng(task['fit_seed']);schedule=[]
    for step in range(task['steps']):
        if step%4==2:index=int(rng.choice(high));group='success_retention'
        elif step%8==7:index=int(rng.choice(mid));group='intermediate_retention'
        else:index=int(rng.choice(failure));group='failure'
        schedule.append((index,group,step%3))
    def fetch(item):
        index,group,_=item;features,_,_=load_features(rows[index],engine.cfg)
        return features,target_for(index) if group=='failure' else None
    folder=ROOT/'behavior_routers'/task['id'];folder.mkdir(parents=True,exist_ok=False)
    trace=[];checkpoints=[];began=time.monotonic();fits=Fits()
    # A scored-response warm start initializes choices; the actual mixture still
    # receives gradients through the downstream network, without linear rewards.
    if task.get('warmup_steps',128):
        from r2_router_features import trajectory_features
        fold='all' if held<0 else f'fold{held}';meta=read(ROOT/'router_features'/fold/'COMPLETE.json')
        with np.load(ROOT/meta['path']) as z:cached=np.array(z['observation'][:,-64:])
        xx=[];yy=[]
        for response_path in task['responses']:
            response=read(ROOT/response_path)
            with np.load(ROOT/response['matrix']) as z:
                ii=np.array(z['global_indices']);arm_ids=list(z['arm_ids']);ss=np.array(z['scores']);tt=np.array(z['trajectory']);aa=np.array(z['base_action_states'])
            assert np.all(train[ii]);pick=[0]+[arm_ids.index(p['id']) for p in parts]
            for j,index in enumerate(ii):
                for n in range(ss.shape[2]):
                    v=[cached[index]]
                    if tier in ['trajectory','denoising']:v.append(trajectory_features(tt[j,0,n]))
                    if tier=='denoising':v.append(aa[j,n].reshape(-1))
                    score=ss[j,pick,n];utility=score[:,0]-score[0,0]
                    if role=='safety':
                        unsafe=(score[:,1]<score[0,1])|(score[:,2]<score[0,2])|((score[:,0]==0)&(score[0,0]>0))
                        utility[unsafe]=-10
                    utility[0]=0;xx.append(np.concatenate(v));yy.append(int(np.argmax(utility)))
        warm_x=torch.as_tensor(np.asarray(xx),device='cuda');warm_y=torch.as_tensor(yy,device='cuda')
        for _ in range(task.get('warmup_steps',128)):
            pick=torch.as_tensor(rng.choice(len(xx),min(len(xx),128)),device='cuda')
            optimizer.zero_grad(set_to_none=True);logits,_=router(warm_x[pick]);loss=torch.nn.functional.cross_entropy(logits,warm_y[pick]);loss.backward()
            torch.nn.utils.clip_grad_norm_(router.parameters(),1.);optimizer.step()
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,schedule[0])
        for step,(index,group,noise) in enumerate(schedule):
            features,target=future.result()
            if step+1<len(schedule):future=reader.submit(fetch,schedule[step+1])
            row=rows[index]
            with torch.no_grad():
                hidden=from_cached(engine,features,index)
                native,states=base_trajectory(engine,features,hidden,seed(row['token'],noise),tier=='denoising')
                if noise==0:assert np.array_equal(native.cpu().numpy(),baseline_row(row)['trajectory'])
                x=current_feature(engine,native,states,held,tier)
            optimizer.zero_grad(set_to_none=True);logits,amount=router(x)
            weights,strength=coefficients(logits,amount,kind,True,temperature=max(.5,1-step/max(task['steps'],1)*.5))
            condition,post,stats=forward(engine,parts,weights,strength,fits)
            prediction=predict_gradient(engine,features,condition,post,seed(row['token'],noise))
            goal=torch.as_tensor(target[1],device='cuda') if target else native.detach()
            trajectory_loss=training_loss(prediction,goal)
            loss=trajectory_loss*(1 if group=='failure' else task.get('retention_weight',3.))
            # No load balancing: weight0 is free to approach one.
            if group!='failure':loss=loss+task.get('abstention_penalty',.002)*(1-torch.softmax(logits,0)[0])
            edit_penalty=torch.stack([s[0].square()/s[1].square().clamp(min=1e-12) for s in stats]).sum()
            loss=loss+.0001*edit_penalty
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(router.parameters(),1.);optimizer.step()
            if step%16==0 or step+1 in task['checkpoints']:
                v=torch.stack([loss.detach(),trajectory_loss.detach(),norm.detach(),weights[0].detach(),edit_penalty.detach()]).cpu().numpy()
                assert np.isfinite(v).all();trace.append(dict(step=step,index=index,noise=noise,group=group,loss=float(v[0]),trajectory_loss=float(v[1]),gradient_norm=float(v[2]),identity_weight=float(v[3]),edit_squared=float(v[4])))
            if step+1 in task['checkpoints']:
                path=folder/('step%04d.npz'%(step+1));h=save_npz(path,**{n:p.detach().cpu().numpy() for n,p in router.state_dict().items()})
                checkpoints.append(dict(step=step+1,path=str(path.relative_to(ROOT)),sha256=h))
    engine.verify_engine()
    result=dict(status='TRAINED_NOT_ACTUAL_PDMS_VALIDATED',time=stamp(),task=task,kind=kind,tier=tier,role=role,
        parts=parts,system=selection['system'],nominal_K=selection['K'],active_K=len(parts),heldout_fold=held,
        input_dimension=dimension,checkpoints=checkpoints,trace=trace,seconds=time.monotonic()-began,
        true_downstream_mixture_training=True,experts_frozen=True,base_frozen=True,exact_identity_available=True,
        no_outcome_additivity_assumed=True,GT_PDMS_not_deployment_inputs=True,validation_fitted=False,test_accessed=False)
    atomic(folder/'TRAINING.json',result)
    return dict(path=str((folder/'TRAINING.json').relative_to(ROOT)),checkpoints=checkpoints,seconds=result['seconds'])


@lru_cache(maxsize=64)
def checkpoint(path,expected,dimension,count):
    import torch
    import numpy as np
    assert sha(ROOT/path)==expected;module=make_model(dimension,count)
    with np.load(ROOT/path) as z:module.load_state_dict({n:torch.as_tensor(np.array(z[n]),device='cuda') for n in z.files})
    module.eval()
    for p in module.parameters():p.requires_grad_(False)
    return module
