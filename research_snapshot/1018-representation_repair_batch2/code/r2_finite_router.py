"""Actual-outcome discrete routing, identity included, frozen K expert actions.

CE continues the original 128-step scored-response warm start. Regret variants
optimize the expected utility of selecting one independently generated complete
candidate. This expectation is not a linear model of hidden-state mixtures.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=8)
def cached_observation(held):
    import numpy as np
    folder='all' if held<0 else 'fold'+str(held);meta=read(ROOT/'router_features'/folder/'COMPLETE.json')
    with np.load(ROOT/meta['path']) as z:return np.array(z['observation'][:,-64:])


def dataset(task):
    import numpy as np
    from r2_router_features import trajectory_features
    selection=read(ROOT/task['selection']);held=selection['heldout_fold'];role=task['role'];tier=task['tier'];by_id={p['id']:p for p in selection['arms']}
    parts=[by_id[v] for _,v in sorted(selection['policies'][role].items(),key=lambda p:int(p[0]))]
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);allowed=np.asarray([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    observation=cached_observation(held);xx=[];yy=[];uu=[];classes=[]
    for response_path in task['responses']:
        response=read(ROOT/response_path);assert read(ROOT/response['point'])['heldout_fold']==held
        with np.load(ROOT/response['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);ss=np.array(z['scores']);tt=np.array(z['trajectory']);states=np.array(z['base_action_states'])
        assert np.all(allowed[ii]);pick=[0]+[ids.index(p['id']) for p in parts]
        for j,index in enumerate(ii):
            for n in range(ss.shape[2]):
                values=[observation[index]]
                if tier in ['trajectory','denoising']:values.append(trajectory_features(tt[j,0,n]))
                if tier=='denoising':values.append(states[j,n].reshape(-1))
                score=ss[j,pick,n];utility=score[:,0]-score[0,0]
                if role=='safety':
                    unsafe=(score[:,1]<score[0,1])|(score[:,2]<score[0,2])|((score[:,0]==0)&(score[0,0]>0));utility[unsafe]=-10
                utility[0]=0.;xx.append(np.concatenate(values));yy.append(int(np.argmax(utility)));uu.append(np.clip(utility,-1,1));classes.append(0 if q[index]<.7 else 1 if q[index]>.9 else 2)
    populations=np.asarray([np.sum(allowed&(q<.7)),np.sum(allowed&(q>.9)),np.sum(allowed&(q>=.7)&(q<=.9))]);counts=np.bincount(classes,minlength=3);assert np.all(counts>0)
    weights=np.asarray([populations[c]/counts[c] for c in classes]);weights/=weights.mean()
    return dict(x=np.asarray(xx),y=np.asarray(yy),utility=np.asarray(uu),weights=weights,parts=parts,selection=selection,rows=rows,quality=q,allowed=allowed)


def initial_rng(task,data):
    """Match exactly the draws consumed before the original warm-start loop."""
    import numpy as np
    rng=np.random.default_rng(task['fit_seed']);q=data['quality'];allowed=data['allowed'];failure=np.flatnonzero(allowed&(q<.7));high=np.flatnonzero(allowed&(q>.9));mid=np.flatnonzero(allowed&(q>=.7)&(q<=.9))
    for step in range(task.get('original_proxy_steps',512)):
        if step%4==2:rng.choice(high)
        elif step%8==7:rng.choice(mid)
        else:rng.choice(failure)
    return rng


def run(engine,task,pool):
    import torch
    import numpy as np
    from common import reseed
    from r2_behavior_router import make_model
    from r2_expert_space import save_npz
    assert task['method'] in ['ce_continuation','regret_uniform','regret_natural']
    data=dataset(task);dimension=data['x'].shape[1];parts=data['parts'];held=data['selection']['heldout_fold']
    reseed(task['fit_seed']);module=make_model(dimension,len(parts));optimizer=torch.optim.AdamW(module.parameters(),lr=.001,weight_decay=.001)
    rng=initial_rng(task,data);x=torch.as_tensor(data['x'],device='cuda');y=torch.as_tensor(data['y'],device='cuda');u=torch.as_tensor(data['utility'],device='cuda',dtype=torch.float32);w=torch.as_tensor(data['weights'],device='cuda',dtype=torch.float32)
    folder=ROOT/'finite_outcome_routers'/task['id'];folder.mkdir(parents=True,exist_ok=False);trace=[];checkpoints=[];began=time.monotonic();warm=task.get('warmup_steps',128)
    for step in range(task['steps']):
        pick=torch.as_tensor(rng.choice(len(x),min(len(x),128)),device='cuda');optimizer.zero_grad(set_to_none=True);logits,amount=module(x[pick])
        if step<warm or task['method']=='ce_continuation':loss=torch.nn.functional.cross_entropy(logits,y[pick]);regret=loss.new_zeros(())
        else:
            ce=torch.nn.functional.cross_entropy(logits,y[pick],reduction='none')
            value=u[pick];probability=torch.softmax(logits,-1);regret_each=value.max(-1).values-(probability*value).sum(-1);importance=w[pick] if task['method']=='regret_natural' else torch.ones_like(regret_each)
            regret=(importance*regret_each).mean();loss=regret+.02*(importance*ce).mean()
        loss.backward();norm=torch.nn.utils.clip_grad_norm_(module.parameters(),1.);optimizer.step()
        if step%64==0 or step+1 in task['checkpoints']:
            values=torch.stack([loss.detach(),regret.detach(),norm.detach()]).cpu().numpy();assert np.isfinite(values).all();trace.append(dict(step=step+1,loss=float(values[0]),regret=float(values[1]),gradient_norm=float(values[2])))
        if step+1 in task['checkpoints']:
            path=folder/('step%05d.npz'%(step+1));hashed=save_npz(path,**{n:p.detach().cpu().numpy() for n,p in module.state_dict().items()});checkpoints.append(dict(step=step+1,path=str(path.relative_to(ROOT)),sha256=hashed))
    engine.verify_engine();record=dict(status='TRAINED_NOT_HELD_POLICY_VALIDATED',time=stamp(),task=task,method=task['method'],heldout_fold=held,system=data['selection']['system'],role=task['role'],tier=task['tier'],parts=parts,input_dimension=dimension,
        nominal_K=data['selection']['K'],active_K=len(parts),checkpoints=checkpoints,trace=trace,seconds=time.monotonic()-began,training_examples=len(x),
        amount_stays_one=True,identity_is_action_zero=True,base_and_experts_frozen=True,true_scored_complete_candidates_only=True,
        no_GT_trajectory_proxy=True,no_linear_hidden_mixture_assumption=True,source_responses=task['responses'],validation_fitted=False,test_accessed=False)
    atomic(folder/'TRAINING.json',record);return dict(path=str((folder/'TRAINING.json').relative_to(ROOT)),seconds=record['seconds'],checkpoints=checkpoints)
