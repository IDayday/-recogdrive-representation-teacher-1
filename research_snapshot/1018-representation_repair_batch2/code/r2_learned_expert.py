"""Outcome-trained low-rank experts through the frozen VLM/action suffix.

The target is an actually scored improved trajectory (or safe GT), never a target
hidden state. Base weights remain frozen; only the internal correction is learned.
"""
from r2_common import *
from functools import lru_cache


@lru_cache(maxsize=1)
def targets():
    # Index only; trajectory payloads are loaded lazily for selected train cases.
    result={}
    for path in (ROOT/'analysis/case_corrections').glob('correction_interface_*.json'):
        name=path.stem;index=int(name.rsplit('_',1)[1]);result.setdefault(index,[]).append(path)
    return result


@lru_cache(maxsize=512)
def target_for(index):
    import numpy as np
    options=[]
    for path in targets().get(index,[]):
        d=read(path);base=d['records'][0];best=d['records'][d['selected_index']];gt=d['records'][-1]
        for candidate in [best,gt]:
            s=candidate['score'];b=base['score']
            safe=(s['no_at_fault_collisions']>=b['no_at_fault_collisions'] and
                  s['drivable_area_compliance']>=b['drivable_area_compliance'])
            if safe and s['score']>b['score']+1e-8:
                if candidate is gt and s['score']<=.9:continue
                options.append((s['score'],np.asarray(candidate['trajectory'],dtype=np.float32)))
    return max(options,key=lambda x:x[0]) if options else None


def make_module(dimension,rank):
    import torch
    class Expert(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.down=torch.nn.Linear(dimension,rank)
            self.up=torch.nn.Linear(rank,dimension)
            torch.nn.init.zeros_(self.up.weight);torch.nn.init.zeros_(self.up.bias)
        def forward(self,value):return self.up(torch.tanh(self.down(value)))
    return Expert().cuda().float()


def training_loss(prediction,target):
    import torch
    scales=prediction.new_tensor([40.,10.])
    return torch.nn.functional.smooth_l1_loss(prediction[:,:2]/scales,target[:,:2]/scales)+.1*(1-torch.cos(prediction[:,2]-target[:,2])).mean()


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from repair_engine import baseline_row
    from r2_counterfactual import edited_value,predict_gradient
    from common import reseed
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    held=task.get('heldout_fold',-1)
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    train=np.array([r['subset']=='exploration' for r in rows])&((folds!=held) if held>=0 else True)
    meta=read(ROOT/task['responsibility_meta']);assert meta['heldout_fold']==held
    with np.load(ROOT/meta['path']) as z:
        indices=np.array(z['global_indices']);weight=np.array(z['responsibility'][:,task['expert']],dtype=np.float64)
    assert np.all(train[indices])
    fit_path=ROOT/task['fit_path'];assert sha(fit_path)==task['fit_sha256']
    assert read(fit_path.with_suffix('.json'))['heldout_fold']==held
    with np.load(fit_path) as z:
        basis=torch.tensor(np.array(z['basis']),device='cuda',dtype=torch.float32)
        center=torch.tensor(np.array(z['center']),device='cuda',dtype=torch.float32)
        scale=torch.tensor(np.array(z['scale']),device='cuda',dtype=torch.float32).clamp(min=1e-4)
    if task.get('space_control')=='full':
        basis=torch.eye(len(center),device='cuda');scale=torch.ones(len(center),device='cuda')
    elif task.get('space_control')=='random':
        rng=np.random.default_rng(task['fit_seed']+991)
        value,_=np.linalg.qr(rng.normal(size=tuple(basis.shape)))
        basis=torch.tensor(value,device='cuda',dtype=torch.float32)
        scale=torch.ones(basis.shape[1],device='cuda')
    reseed(task['fit_seed'])
    module=make_module(basis.shape[1],task['rank'])
    optimizer=torch.optim.AdamW(module.parameters(),lr=task.get('learning_rate',.003),weight_decay=1e-4)
    rng=np.random.default_rng(task['fit_seed']);weight=weight/weight.sum()
    high=np.flatnonzero(train&(q>.9));middle=np.flatnonzero(train&(q>=.7)&(q<=.9))
    records=[];checkpoints=[];began=time.monotonic()
    destination=ROOT/'learned_experts'/task['id'];destination.mkdir(parents=True,exist_ok=False)
    for step in range(task['steps']):
        # Identity retention is trained on actual Base successes, alongside the
        # subgroup failures. Unresponsive failures are retained as Base targets.
        if step%4==2:index=int(rng.choice(high));kind='success_retention'
        elif step%8==7:index=int(rng.choice(middle));kind='intermediate_retention'
        else:index=int(rng.choice(indices,p=weight));kind='subgroup_failure'
        row=rows[index];features=raw_features(row)
        with torch.no_grad():
            hidden=engine.forward_native(features)
            native=engine.trajectory(features,hidden,seed(row['token']))
        assert np.array_equal(native.cpu().numpy(),baseline_row(row)['trajectory'])
        choice=target_for(index) if kind=='subgroup_failure' else None
        target=torch.tensor(choice[1],device='cuda') if choice else native.detach()
        original=engine.prefix[task['block']];mask,valid=engine.mask(task['block'],task['group'])
        if not valid:
            records.append(dict(step=step,index=index,skipped='missing token group'));continue
        pooled=original.reshape(-1,original.shape[-1])[mask].float().mean(0)
        encoded=((pooled-center)@basis)/scale
        optimizer.zero_grad(set_to_none=True)
        delta=basis@module(encoded)
        changed,metrics=edited_value(engine,task['block'],task['group'],delta,task['cap'])
        condition,interface=engine.suffix(task['block'],changed)
        prediction=predict_gradient(engine,features,condition,interface,seed(row['token']))
        loss=training_loss(prediction,target)
        # Explicit penalty is dimensionless and does not replace real outcome
        # checks. It controls intervention magnitude within the hard norm cap.
        loss=loss+task.get('edit_penalty',.0001)*delta.square().mean()/pooled.square().mean().clamp(min=1e-8)
        if kind!='subgroup_failure':loss=loss*task.get('retention_weight',2.)
        assert torch.isfinite(loss);loss.backward()
        gradients=[p.grad for p in module.parameters() if p.grad is not None]
        assert gradients and all(torch.isfinite(g).all() for g in gradients)
        norm=torch.nn.utils.clip_grad_norm_(module.parameters(),1.)
        optimizer.step();engine.verify_engine()
        records.append(dict(step=step,index=index,token=row['token'],kind=kind,
                            improved_target=choice is not None,target_score=choice[0] if choice else row['quality'],
                            loss=float(loss.detach()),gradient_norm=float(norm),relative_edit=metrics['relative_edit']))
        if step+1 in task.get('checkpoints',[task['steps']]):
            path=destination/('step%04d.npz'%(step+1))
            arrays={n:p.detach().cpu().numpy() for n,p in module.state_dict().items()}
            arrays.update(basis=basis.cpu().numpy(),center=center.cpu().numpy(),scale=scale.cpu().numpy())
            with path.open('wb') as f:np.savez(f,**arrays)
            checkpoints.append(dict(step=step+1,path=str(path.relative_to(ROOT)),sha256=sha(path)))
    result=dict(status='TRAINED_NOT_EVALUATED',time=stamp(),task=task,seconds=time.monotonic()-began,
                records=records,checkpoints=checkpoints,base_weights_frozen=True,
                training_signal='Final trajectory through frozen suffix and native denoising, not hidden-state MSE',
                target_source='Actually rescored better correction or GT>90; otherwise preserve Base',
                actual_pdms_must_be_evaluated=True,heldout_fold=held,validation_fitted=False,test_accessed=False)
    atomic(destination/'TRAINING.json',result)
    return dict(path=str((destination/'TRAINING.json').relative_to(ROOT)),checkpoints=checkpoints,seconds=result['seconds'])


@lru_cache(maxsize=64)
def checkpoint_arrays(path,expected_hash):
    import torch
    import numpy as np
    assert sha(ROOT/path)==expected_hash
    with np.load(ROOT/path) as z:
        return {n:torch.tensor(np.array(z[n]),device='cuda',dtype=torch.float32) for n in z.files}


def apply(engine,task,checkpoint,strength=1.):
    """Deployable local correction; no GT, quality score, or group label needed."""
    import torch
    arrays=checkpoint_arrays(checkpoint['path'],checkpoint['sha256'])
    from r2_counterfactual import edited_value
    h=engine.prefix[task['block']];mask,valid=engine.mask(task['block'],task['group'])
    if not valid:return h,dict(relative_edit=0.)
    pooled=h.reshape(-1,h.shape[-1])[mask].float().mean(0)
    p=(pooled-arrays['center'])@arrays['basis']/arrays['scale']
    value=torch.nn.functional.linear(torch.tanh(torch.nn.functional.linear(p,arrays['down.weight'],arrays['down.bias'])),arrays['up.weight'],arrays['up.bias'])
    return edited_value(engine,task['block'],task['group'],arrays['basis']@value*strength,task['cap']*strength)
