"""Independent cached-interface behavior runtime, with unchanged paired sampler.

Existing experiments keep their original runtime. Only this new version overlaps
deterministic CPU feature preparation with GPU computation and batches logging
synchronization. Every checkpoint is still evaluated by true independent PDMS.
"""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def edit(engine,block,group,delta,cap):
    import torch
    h=engine.prefix[block];mask,valid=engine.mask(block,group)
    assert valid
    flat=h.reshape(-1,h.shape[-1]);selected=flat[mask].float();limit=cap*selected.norm()
    shift=delta*torch.clamp(limit/(delta.norm().clamp(min=1e-12)*len(selected)**.5),max=1.)
    for _ in range(3):
        trial=(selected+shift).to(h.dtype);norm=(trial.float()-selected).norm()
        shift=shift*torch.clamp(limit/norm.detach().clamp(min=1e-12)*.999,max=1.)
    trial=(selected+shift).to(h.dtype);norm=(trial.float()-selected).norm()
    trial=torch.where(norm.detach()<=limit+1e-7,trial,flat[mask]);out=flat.clone();out[mask]=trial
    return out.reshape_as(h),(trial.float()-selected).norm()/selected.norm().clamp(min=1e-12)


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_learned_expert import target_for,make_module,training_loss
    from worker import load_features
    from r2_cached_interfaces import from_cached
    from r2_native_cache import native as replay_native
    from repair_engine import baseline_row
    from r2_counterfactual import predict_gradient
    from common import reseed
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    assert task['block'] in ['interface_pre','interface_post']
    held=task.get('heldout_fold',-1);meta=read(ROOT/task['responsibility_meta']);assert meta['heldout_fold']==held
    train=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    with np.load(ROOT/meta['path']) as z:
        indices=np.array(z['global_indices']);prob=np.array(z['responsibility'][:,task['expert']],dtype=np.float64)
    assert np.all(train[indices]);prob/=prob.sum()
    fit_path=ROOT/task['fit_path'];assert sha(fit_path)==task['fit_sha256']
    assert read(fit_path.with_suffix('.json'))['heldout_fold']==held
    with np.load(fit_path) as z:
        basis=torch.tensor(np.array(z['basis']),device='cuda',dtype=torch.float32)
        center=torch.tensor(np.array(z['center']),device='cuda',dtype=torch.float32)
        scale=torch.tensor(np.array(z['scale']),device='cuda',dtype=torch.float32).clamp(min=1e-4)
    if task.get('space_control')=='full':
        basis=torch.eye(len(center),device='cuda');scale=torch.ones(len(center),device='cuda')
    elif task.get('space_control')=='random':
        rng_control=np.random.default_rng(task['fit_seed']+991)
        random_basis,_=np.linalg.qr(rng_control.normal(size=tuple(basis.shape)))
        basis=torch.tensor(random_basis,device='cuda',dtype=torch.float32)
        scale=torch.ones(basis.shape[1],device='cuda')
    reseed(task['fit_seed']);module=make_module(basis.shape[1],task['rank'])
    optimizer=torch.optim.AdamW(module.parameters(),lr=task.get('learning_rate',.003),weight_decay=1e-4)
    high=np.flatnonzero(train&(q>.9));middle=np.flatnonzero(train&(q>=.7)&(q<=.9));rng=np.random.default_rng(task['fit_seed'])
    schedule=[]
    for step in range(task['steps']):
        if step%4==2:index=int(rng.choice(high));kind='success_retention'
        elif step%8==7:index=int(rng.choice(middle));kind='intermediate_retention'
        else:index=int(rng.choice(indices,p=prob));kind='subgroup_failure'
        noise=int(task.get('training_noise_indices',[0,1,2])[step%len(task.get('training_noise_indices',[0,1,2]))])
        schedule.append((index,kind,noise))
    def fetch(item):
        began=time.monotonic();index,kind,noise=item
        features,_,_=load_features(rows[index],engine.cfg);choice=target_for(index) if kind=='subgroup_failure' else None
        return features,choice,time.monotonic()-began
    destination=ROOT/'learned_experts'/task['id'];destination.mkdir(parents=True,exist_ok=False)
    trace=[];checkpoints=[];began=time.monotonic();read_seconds=0.;input_wait=0.
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,schedule[0])
        for step,item in enumerate(schedule):
            index,kind,noise=item;row=rows[index];started=time.monotonic()
            features,choice,seconds=future.result();input_wait+=time.monotonic()-started;read_seconds+=seconds
            if step+1<len(schedule):future=reader.submit(fetch,schedule[step+1])
            with torch.no_grad():
                hidden=from_cached(engine,features,index)
                native,_=replay_native(engine,features,hidden,row,noise,False)
            if noise==0:assert np.array_equal(native.cpu().numpy(),baseline_row(row)['trajectory'])
            target=torch.tensor(choice[1],device='cuda') if choice else native.detach()
            original=engine.prefix[task['block']];mask,valid=engine.mask(task['block'],task['group']);assert valid
            pooled=original.reshape(-1,original.shape[-1])[mask].float().mean(0)
            optimizer.zero_grad(set_to_none=True);delta=basis@module(((pooled-center)@basis)/scale)
            changed,relative=edit(engine,task['block'],task['group'],delta,task['cap'])
            condition,interface=engine.suffix(task['block'],changed)
            prediction=predict_gradient(engine,features,condition,interface,seed(row['token'],noise))
            if step==0:assert torch.equal(prediction.detach(),native),'New training runtime zero edit changed the sampler'
            loss=training_loss(prediction,target)+task.get('edit_penalty',.0001)*delta.square().mean()/pooled.square().mean().clamp(min=1e-8)
            if kind!='subgroup_failure':loss=loss*task.get('retention_weight',2.)
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(module.parameters(),1.)
            optimizer.step();engine.verify_engine()
            logging=step%8==0 or step+1 in task['checkpoints'] or step==task['steps']-1
            if logging:
                metrics=torch.stack([loss.detach(),norm.detach(),relative.detach()]).float().cpu().numpy()
                assert np.isfinite(metrics).all() and metrics[2]<=task['cap']+1e-6
                trace.append(dict(step=step,index=index,token=row['token'],kind=kind,seed_index=noise,
                                  improved_target=choice is not None,target_score=choice[0] if choice else float(q[index]),
                                  loss=float(metrics[0]),gradient_norm=float(metrics[1]),relative_edit=float(metrics[2])))
            if step+1 in task['checkpoints']:
                path=destination/('step%04d.npz'%(step+1));arrays={n:p.detach().cpu().numpy() for n,p in module.state_dict().items()}
                assert all(np.isfinite(a).all() for a in arrays.values())
                arrays.update(basis=basis.cpu().numpy(),center=center.cpu().numpy(),scale=scale.cpu().numpy())
                with path.open('wb') as f:np.savez(f,**arrays)
                checkpoints.append(dict(step=step+1,path=str(path.relative_to(ROOT)),sha256=sha(path)))
    result=dict(status='TRAINED_NOT_EVALUATED',time=stamp(),task=task,seconds=time.monotonic()-began,records=trace,
                checkpoints=checkpoints,base_weights_frozen=True,read_decode_cpu_seconds=read_seconds,input_wait_seconds=input_wait,
                cached_interface=True,prefetch=True,native_replay=True,native_cache_counts=dict(engine.immutable_native_counts),training_noise_indices=task.get('training_noise_indices',[0,1,2]),
                training_signal='Final trajectory loss through native suffix and denoising; actual PDMS evaluation required',
                heldout_fold=held,validation_fitted=False,test_accessed=False)
    atomic(destination/'TRAINING.json',result)
    return dict(path=str((destination/'TRAINING.json').relative_to(ROOT)),seconds=result['seconds'],checkpoints=checkpoints,
                read_decode_cpu_seconds=read_seconds,input_wait_seconds=input_wait)
