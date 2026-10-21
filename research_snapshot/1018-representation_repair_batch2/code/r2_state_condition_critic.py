"""Matched continuation: fixed critic start/budget/class frequency, old vs new cases.

Independent artifact namespace; never discovered as an original eight-thousand
step critic. Both arms use the same original two-bank class proportions.
"""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import numpy as np
    import torch
    from common import reseed
    from worker import load_features
    from repair_engine import baseline_row
    from r2_cached_interfaces import from_cached
    from r2_context_critic import make_model,inner_session
    from r2_point_response import FIELDS
    from r2_expert_space import save_npz
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);held=task['heldout_fold']
    allowed=np.asarray([r['subset']=='exploration' and int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held and not inner_session(r['session']) for r in rows])
    cases=np.flatnonzero(allowed);failures=np.flatnonzero(allowed&(q<.7));classes=np.where(q<.7,0,np.where(q>.9,1,2));banks={};paths=[];lineage=[]
    for actual,reference in zip(task['responses'],task['reference_responses']):
        arrays=[]
        for path in [actual,reference]:
            meta=read(ROOT/path);assert sha(ROOT/meta['matrix'])==meta['matrix_sha256']
            with np.load(ROOT/meta['matrix']) as z:d={k:np.array(z[k]) for k in ['global_indices','seeds','scores','trajectory','arm_ids']}
            assert np.all([rows[int(i)]['subset']=='exploration' for i in d['global_indices']]);arrays.append(d)
        d,ref=arrays;assert list(d['arm_ids'])==list(ref['arm_ids']) and list(d['seeds'])==list(ref['seeds'])
        eligible=allowed[d['global_indices']];reference_positions=np.flatnonzero(allowed[ref['global_indices']]);counts=np.bincount(classes[ref['global_indices'][reference_positions]],minlength=3)
        probability=counts/counts.sum();positions=[np.flatnonzero(eligible&(classes[d['global_indices']]==c)) for c in range(3)]
        assert all(len(p)>0 for p in positions);banks[actual]=d;paths.append((actual,positions,probability))
        lineage.append(dict(path=actual,sha256=sha(ROOT/actual),reference=reference,class_probability=probability.tolist(),eligible_counts=[len(p) for p in positions]))
    rng=np.random.default_rng(task['fit_seed']);schedule=[]
    for step in range(task['steps']):
        if step%4<2:
            path,positions,prob=paths[int(rng.integers(len(paths)))];c=int(rng.choice(3,p=prob));j=int(rng.choice(positions[c]));d=banks[path]
            arm=int(rng.integers(1,len(d['arm_ids'])));n=int(rng.integers(len(d['seeds'])));schedule.append((int(d['global_indices'][j]),path,j,arm,n))
        else:schedule.append((int(rng.choice(failures if step%4==2 else cases)),None,None,None,None))
    def fetch(item):
        index,path,j,arm,n=item;features,_,_=load_features(rows[index],engine.cfg)
        if path:
            d=banks[path];return features,d['trajectory'][j,[0,arm],n],d['scores'][j,[0,arm],n],int(d['seeds'][n])
        base=baseline_row(rows[index]);tr=np.asarray(base['trajectory'],np.float32);score=np.asarray([base['score'][f] for f in FIELDS],np.float32)
        return features,np.stack([tr,tr]),np.stack([score,score]),0
    reseed(task['fit_seed']);view=task['context_view'];model=make_model(1536 if view.startswith('pre') else 384);ck=task['initial_checkpoint'];assert sha(ROOT/ck['path'])==ck['sha256']
    with np.load(ROOT/ck['path']) as z:model.load_state_dict({k:torch.as_tensor(np.array(z[k]),device='cuda') for k in z.files})
    optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.001);destination=ROOT/'state_condition_critics'/task['id'];destination.mkdir(parents=True,exist_ok=False)
    trace=[];checkpoints=[];began=time.monotonic();waiting=0.
    with ThreadPoolExecutor(max_workers=4) as reader:
        futures={j:reader.submit(fetch,schedule[j]) for j in range(min(8,len(schedule)))}
        for step,item in enumerate(schedule):
            t=time.monotonic();features,trajectory,score,noise=futures.pop(step).result();waiting+=time.monotonic()-t
            if step+8<len(schedule):futures[step+8]=reader.submit(fetch,schedule[step+8])
            index=item[0];assert allowed[index]
            with torch.no_grad():
                hidden=from_cached(engine,features,index);site='interface_pre' if view.startswith('pre') else 'interface_post';group='all_mean' if view.endswith('all') else 'valid_mean'
                h=engine.prefix[site];mask,valid=engine.mask(site,group);assert valid;context=h.reshape(-1,h.shape[-1])[mask].detach()
                from r2_state_condition_context import append as append_conditions
                context=append_conditions(engine,features,context,task['state_mode'])
                candidate=torch.as_tensor(trajectory,device='cuda');target=torch.as_tensor(score,device='cuda',dtype=torch.float32)
                if step==0:assert np.array_equal(engine.trajectory(features,hidden,seed(rows[index]['token'],noise)).cpu().numpy(),trajectory[0])
            optimizer.zero_grad(set_to_none=True);prediction=model(context,candidate)
            absolute=torch.nn.functional.mse_loss(prediction[:,0],target[:,0])+.5*torch.nn.functional.binary_cross_entropy(prediction[:,1:3],target[:,1:3])
            absolute=absolute+.2*torch.nn.functional.binary_cross_entropy(prediction[:,3],target[:,3])+.2*torch.nn.functional.mse_loss(prediction[:,4],target[:,4])+.05*torch.nn.functional.mse_loss(prediction[:,5:],target[:,5:])
            pair=torch.nn.functional.mse_loss(prediction[1,0]-prediction[0,0],target[1,0]-target[0,0]);loss=absolute+2*pair;loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
            if step%32==0 or step+1 in task['checkpoints']:
                values=torch.stack([loss.detach(),absolute.detach(),pair.detach(),norm.detach()]).cpu().numpy();assert np.isfinite(values).all()
                trace.append(dict(step=step+1,index=index,candidate_source=item[1],seed_index=noise,loss=float(values[0]),absolute_loss=float(values[1]),gain_loss=float(values[2]),gradient_norm=float(values[3])))
            if (step+1)%1024==0:atomic(destination/'LIVE.json',dict(time=stamp(),step=step+1,steps=task['steps'],seconds=time.monotonic()-began,input_wait_seconds=waiting))
            if step+1 in task['checkpoints']:
                path=destination/('additional_step%05d.npz'%(step+1));hashed=save_npz(path,**{k:p.detach().cpu().numpy() for k,p in model.state_dict().items()});checkpoints.append(dict(step=8000+step+1,additional_steps=step+1,path=str(path.relative_to(ROOT)),sha256=hashed))
    engine.verify_engine();record=dict(status='TRAINED_NOT_HELDOUT_CONFIRMED',time=stamp(),task=task,heldout_fold=held,context_view=view,fit_seed=task['fit_seed'],checkpoints=checkpoints,trace=trace,seconds=time.monotonic()-began,input_wait_seconds=waiting,
        source_responses=lineage,initial_checkpoint=ck,optimizer_reset_in_both_arms=True,matched_class_sampling=True,inner_calibration_excluded=True,exact_Base_guard=True,validation_accessed=False,test_accessed=False)
    atomic(destination/'TRAINING.json',record);return dict(path=str((destination/'TRAINING.json').relative_to(ROOT)),seconds=record['seconds'],checkpoints=checkpoints)
