"""Frozen RL observation adapter: paired noise, correctly indexed continuation, read-only hooks.

No changes to the released model, baseline sampler, or parameters. The adapter calls
the original p_mean_variance and changes only the explicitly recorded starting index.
"""
from common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import subprocess
import traceback


def noise_seed(token, group, component):
    return int(hashlib.sha256(f'{token}|20261016|P{group}|{component}'.encode()).hexdigest()[:8],16)


def noise_bank(token, group, timesteps):
    import torch
    components=['initial']+[f'step-{t}' for t in timesteps]
    seeds={c:noise_seed(token,group,c) for c in components}
    # CPU generators give an explicit, device-count-independent bank. Save actual tensors too.
    bank={c:torch.randn((1,8,3),generator=torch.Generator(device='cpu').manual_seed(s)).cuda()
          for c,s in seeds.items()}
    return bank,seeds


def conditions(head, features):
    batch={k:v.unsqueeze(0).cuda().float() for k,v in features.items()}
    return (head.feature_encoder(batch['last_hidden_state']),
            head.his_traj_encoder(batch['history_trajectory'].reshape(1,1,12)).repeat(1,8,1),
            head.ego_status_encoder(batch['status_feature']))


def modules(head):
    return [('action_encoder',head.action_encoder),('condition_fusion',head.fusion_projector)]+[
        (f'dit_{i:02d}',block) for i,block in enumerate(head.model.transformer_blocks)]


def continue_chain(head, cond, initial, start_index, step_noise, capture=True):
    import torch
    snapshots=[];latent=[];predictions=[];decoder=[];dit_output=[];handles=[];this_step={}
    named=modules(head)
    def hook(name):
        def save(module, inputs, output):
            assert name not in this_step
            this_step[name]=output.detach().clone()
        return save
    if capture:
        handles=[module.register_forward_hook(hook(name)) for name,module in named]
        handles.append(head.action_decoder.register_forward_hook(hook('predicted_noise')))
        handles.append(head.model.final_layer.register_forward_hook(hook('dit_output')))
    current=initial.clone()
    try:
        for i in range(start_index,head.ddim_steps):
            this_step.clear()
            latent.append(current.detach().clone())
            t=head.make_timesteps(1,head.ddim_t[i],current.device)
            index=head.make_timesteps(1,i,current.device)
            mean,logvar,x0=head.p_mean_variance(current,t,index,*cond,deterministic=False)
            std=torch.exp(.5*logvar).to(current.dtype).clamp(min=getattr(head,'eval_min_sampling_denoising_std',.0001))
            clip=getattr(head,'eval_randn_clip_value',1.)
            current=mean+std*step_noise[i].clone().clamp_(-clip,clip)
            predictions.append(x0.detach().clone())
            if capture:
                assert set(this_step)=={n for n,_ in named}|{'predicted_noise','dit_output'}
                snapshots.append(torch.stack([this_step[n].squeeze(0) for n,_ in named]))
                decoder.append(this_step['predicted_noise'].squeeze(0))
                dit_output.append(this_step['dit_output'].squeeze(0))
        current.clamp_(-getattr(head,'final_action_clip_value',1.),getattr(head,'final_action_clip_value',1.))
        trajectory=head.denorm_odo(current).squeeze(0).float().cpu().numpy()
        extra=dict(latents=torch.stack(latent).squeeze(1).cpu().numpy(),
                   reconstructed_x0=torch.stack(predictions).squeeze(1).cpu().numpy())
        if capture:
            extra.update(representations=torch.stack(snapshots).float().cpu().numpy(),
                         predicted_noise=torch.stack(decoder).float().cpu().numpy(),
                         dit_output=torch.stack(dit_output).float().cpu().numpy())
        return trajectory,extra
    finally:
        for h in handles:h.remove()


def save_arrays(path, **arrays):
    import numpy as np
    path=Path(path).resolve();assert path.is_relative_to(ROOT)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    def write():
        with tmp.open('wb') as stream:np.savez(stream,**arrays)
        tmp.replace(path)
    retry(write)


def engineer(args):
    import numpy as np
    import torch
    from transformers import BatchFeature
    from worker import load_model,load_features
    cfg=read(ROOT/'configs/baseline.json')
    references=read(args.references);ref=references[0]
    out=ROOT/'runs'/args.run;out.mkdir(parents=True,exist_ok=True)
    assert not (out/'COMPLETE.json').exists()
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    agent,runtime=load_model(cfg);head=agent.action_head
    versions={k:v._version for k,v in agent.named_parameters()}
    features,_,meta=load_features(ref,cfg)
    assert meta['feature_sha256']==ref['feature_sha256']
    with torch.no_grad(),torch.autocast('cuda',enabled=False):
        cond=conditions(head,features)
        initial=torch.as_tensor(ref['trajectory'],dtype=torch.float32,device='cuda').unsqueeze(0)
        initial=head.norm_odo(initial)
        # Replay original get_action, recording its true pre-step states.
        old=head.p_mean_variance;states=[]
        def wrapped(x,*pos,**kw):
            states.append(x.detach().clone())
            return old(x,*pos,**kw)
        head.p_mean_variance=wrapped
        action=BatchFeature(dict(his_traj=features['history_trajectory'].reshape(1,12).cuda(),
                                 status_feature=features['status_feature'].unsqueeze(0).cuda()))
        value=noise_seed(ref['token'],0,'engineering-parity')
        try:
            reseed(value)
            expected=head.get_action(features['last_hidden_state'].unsqueeze(0).cuda(),action,
                                     init_actions=initial.clone(),deterministic=False)['pred_traj'].squeeze(0).cpu().numpy()
        finally:head.p_mean_variance=old
        reseed(value);steps=[torch.randn_like(initial) for _ in range(head.ddim_steps)]
        parity=[]
        for i in range(head.ddim_steps):
            actual,hidden=continue_chain(head,cond,states[i],i,steps,capture=True)
            plain,_=continue_chain(head,cond,states[i],i,steps,capture=False)
            assert np.array_equal(actual,expected),(i,float(np.abs(actual-expected).max()))
            assert np.array_equal(actual,plain)
            assert np.isfinite(hidden['representations']).all()
            assert hidden['representations'].dtype==np.float32
            parity.append(dict(index=i,t=int(head.ddim_t[i]),max_output_difference=0,
                               representation_shape=list(hidden['representations'].shape)))
        bank,seeds=noise_bank(ref['token'],0,head.ddim_t.tolist())
        steps=[bank[f'step-{int(t)}'] for t in head.ddim_t]
        alpha=head.ddim_alphas[2]
        noised=alpha.sqrt()*initial+(1-alpha).sqrt()*bank['initial']
        a,_=continue_chain(head,cond,noised,2,steps)
        b,_=continue_chain(head,cond,noised,2,steps)
        assert np.array_equal(a,b)
    assert versions=={k:v._version for k,v in agent.named_parameters()}
    assert all(p.grad is None for p in agent.parameters())
    atomic(out/'COMPLETE.json',dict(status='PASS',time=stamp(),token=ref['token'],runtime=runtime,
        original_sampler_and_every_resume_index_exact=parity,hooks_do_not_change_output=True,
        paired_noise_replay_exact=True,parameters_unchanged=True,no_gradients=True,
        layers=[n for n,_ in modules(head)],feature_sha256=meta['feature_sha256'],noise_seeds=seeds))
    print(json.dumps(dict(status='PASS',indices=len(parity),layers=len(modules(head)))),flush=True)


def collect(args):
    import numpy as np
    import torch
    from worker import load_model,load_features
    from representation_prepare import score_init,score_physical
    cfg=read(ROOT/'configs/baseline.json');protocol=read(args.protocol)
    assert digest({k:v for k,v in protocol.items() if k!='identity'})==protocol['identity']
    references=read(args.references)
    if args.phase=='pilot':
        selected=set(protocol['pilot_tokens']);references=[r for r in references if r['token'] in selected]
        assert len(references)==len(selected)
    panel=references[args.rank::args.world_size]
    out=ROOT/'runs'/args.run/args.phase/f'rank{args.rank:03d}';out.mkdir(parents=True,exist_ok=True)
    assert not (out/'COMPLETE.json').exists()
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    agent,runtime=load_model(cfg);head=agent.action_head
    atomic(out/'runtime.json',runtime)
    versions={k:v._version for k,v in agent.named_parameters()}
    steps_t=head.ddim_t.tolist();began=time.monotonic();all_records=[]
    with ProcessPoolExecutor(max_workers=args.scoring_workers,mp_context=mp.get_context('spawn'),initializer=score_init) as pool:
        for count,ref in enumerate(panel,1):
            destination=out/'scenes'/f'{ref["token"]}.json'
            if destination.exists():
                cached=read(destination);assert cached['identity']==protocol['identity']
                all_records.extend(cached['records']);continue
            features,gt,meta=load_features(ref,cfg)
            assert meta['feature_sha256']==ref['feature_sha256'] and meta['target_sha256']==ref['target_sha256']
            assert np.array_equal(gt.double().numpy(),np.asarray(ref['gt_trajectory']))
            pending=[]
            with torch.no_grad(),torch.autocast('cuda',enabled=False):
                cond=conditions(head,features)
                for group in protocol['noise_groups']:
                    bank,seeds=noise_bank(ref['token'],group,steps_t)
                    steps=[bank[f'step-{t}'] for t in steps_t]
                    for t0 in protocol[f'{args.phase}_start_timesteps']:
                        i=steps_t.index(t0);alpha=head.ddim_alphas[i]
                        assert torch.equal(alpha,head.ddpm_alphas_cumprod[t0])
                        extras=[];trajectories=[]
                        for source,trajectory in [('baseline_failure',ref['trajectory']),('GT',ref['gt_trajectory'])]:
                            normalized=head.norm_odo(torch.tensor(trajectory,dtype=torch.float32,device='cuda').unsqueeze(0))
                            initial=alpha.sqrt()*normalized+(1-alpha).sqrt()*bank['initial']
                            final,extra=continue_chain(head,cond,initial,i,steps,capture=True)
                            assert final.shape==(8,3) and np.isfinite(final).all()
                            assert np.isfinite(extra['representations']).all()
                            trajectories.append(final);extras.append(extra)
                        array_path=out/'arrays'/f'{ref["token"]}_P{group}_t{t0}.npz'
                        arrays={k:np.stack([e[k] for e in extras]) for k in extras[0]}
                        save_arrays(array_path,**arrays,final_trajectories=np.stack(trajectories),
                                    initial_noise=bank['initial'].squeeze(0).cpu().numpy(),
                                    step_noise=torch.stack(steps).squeeze(1).cpu().numpy(),
                                    timesteps=np.asarray(steps_t[i:],dtype=np.int64))
                        file_hash=sha(array_path)
                        for source,final in zip(['baseline_failure','GT'],trajectories):
                            r=dict(token=ref['token'],session=ref['session'],subset=ref['subset'],
                                log_name=ref['log_name'],primary_mode=ref['primary_mode'],failure_modes=ref['failure_modes'],
                                source=source,noise_group=group,noise_seeds=seeds,start_t=t0,executed_timesteps=steps_t[i:],
                                trajectory=final.tolist(),array_path=str(array_path),array_sha256=file_hash,
                                branch_index=0 if source=='baseline_failure' else 1,
                                feature_sha256=meta['feature_sha256'],target_sha256=meta['target_sha256'],
                                original_baseline_score=ref['score'],original_gt_score=ref['gt_score'],
                                checkpoint_sha256=cfg['checkpoint_sha256'],identity=protocol['identity'])
                            task=dict(token=ref['token'],source=source,trajectory=r['trajectory'],metric_cache=ref['metric_cache'],
                                      metric_sha256=ref['metric_sha256'],scoring=cfg['scoring'])
                            pending.append((pool.submit(score_physical,task),r))
            records=[]
            for future,r in pending:
                result=future.result(timeout=300);assert result['reference_sha256']==ref['reference_sha256']
                r.update(score=result['score'],quality=quality(result['score']['score']))
                records.append(r)
            atomic(destination,dict(token=ref['token'],identity=protocol['identity'],records=records))
            all_records.extend(records)
            atomic(out/'STATUS.json',dict(status='COLLECTING',time=stamp(),completed=count,total=len(panel),
                                         candidates=len(all_records),seconds=time.monotonic()-began))
            print(json.dumps(dict(rank=args.rank,completed=count,total=len(panel),seconds=time.monotonic()-began)),flush=True)
    assert versions=={k:v._version for k,v in agent.named_parameters()}
    assert all(p.grad is None for p in agent.parameters())
    atomic(out/'records.json',all_records)
    atomic(out/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),scenes=len(panel),candidates=len(all_records),
        identity=protocol['identity'],seconds=time.monotonic()-began,layers=[n for n,_ in modules(head)],
        parameters_unchanged=True,no_gradients=True))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['engineer','collect'])
    parser.add_argument('--run',required=True);parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--protocol',type=Path);parser.add_argument('--phase',choices=['pilot','formal'],default='pilot')
    parser.add_argument('--rank',type=int,default=0);parser.add_argument('--world-size',type=int,default=1)
    parser.add_argument('--scoring-workers',type=int,default=2)
    args=parser.parse_args();setup(f'{args.run}/{args.phase}/rank{args.rank}');compatibility()
    try:
        if args.command=='engineer':engineer(args)
        else:collect(args)
    except BaseException as e:
        atomic(ROOT/'runs'/args.run/f'FAILED_{args.phase}_rank{args.rank}.json',dict(status='FAILED',time=stamp(),
               error=repr(e),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':main()
