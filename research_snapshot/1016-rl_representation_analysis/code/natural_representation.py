"""Route ONE: original natural model S0 outputs, never GT-initialized candidates.

Replay frozen baseline exactly, capture original get_action, and accumulate exact
float64 sufficient statistics while representations are resident in memory.
"""
from common import *
import argparse
from collections import Counter
import csv
import io
import subprocess
import traceback


def write_npz(path,**arrays):
    import numpy as np
    path=Path(path).resolve();assert path.is_relative_to(ROOT)
    path.parent.mkdir(parents=True,exist_ok=True)
    def run():
        tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
        digest=hashlib.sha256()
        with tmp.open('wb') as stream:
            # Non-seekable stream makes ZipFile use descriptors; hash each byte once.
            class Hashed:
                def write(self,data):digest.update(data);return stream.write(data)
                def flush(self):stream.flush()
                def read(self,*args):raise io.UnsupportedOperation('write-only stream')
            np.savez(Hashed(),**arrays)
        tmp.replace(path)
        return digest.hexdigest()
    return retry(run)


def prepare():
    from worker import population
    from representation_prepare import session
    cfg=read(ROOT/'configs/baseline.json');execution=read(ROOT/'configs/execution.json')
    rows=population();scores=list(csv.DictReader((ROOT/'runs'/execution['run_id']/'delivery/scores.csv').open()))
    assert [r['token'] for r in rows]==[r['token'] for r in scores]
    sessions=sorted({session(r['log_name']) for r in rows},key=lambda s:digest({'session':s,'split_seed':20261016}))
    validation=set(sessions[:round(len(sessions)*.2)])
    manifest=[]
    for index,(r,s) in enumerate(zip(rows,scores)):
        assert int(s['seed'])==seed(r['token']) and int(s['rank'])==index%32
        manifest.append(dict(r,global_index=index,session=session(r['log_name']),
            subset='validation' if session(r['log_name']) in validation else 'exploration',
            quality=s['quality'],baseline_pdms_100=float(s['pdms_100']),feature_sha256=s['feature_sha256']))
    atomic(ROOT/'manifests/natural_s0.json',manifest)
    anchors=[next(r['token'] for r in manifest if r['quality']==label) for label in ['high_quality','failure','intermediate']]
    protocol=dict(schema=1,time=stamp(),route='route_one_natural_model_success_failure',source='original natural RL S0 get_action without init_actions',
        baseline_run=execution['run_id'],baseline_identity=cfg['identity'],manifest='manifests/natural_s0.json',manifest_sha256=sha(ROOT/'manifests/natural_s0.json'),
        samples=len(rows),counts=dict(Counter(r['quality'] for r in manifest)),anchors=anchors,
        seed_index=0,seed_formula=cfg['seed_formula'],steps=cfg['expected_timesteps'],layers=18,hidden_dim=384,dit_output_dim=512,
        precision='float32 representations; float64 sums/second moments',chunk_size=32,nodes=2,devices_per_node=16,
        capture='all 5 native steps, all 18 common stages and separate 512D output, all 8 action tokens',
        trajectory_acceptance='every captured trajectory must equal original saved S0 trajectory exactly, not tolerance only',
        labels='original final S0 PDMS, only after exact trajectory replay; high>90 fail<70 middle retained',
        gt_initialization=False,paired_route2_candidates=False,scoring_reuse='reuse original scores ONLY on exact saved-trajectory replay',
        stats='per subset and final quality: n,sum_h,hTh,sum_y,sum_y2,sum_hy; double precision; merge by rank',
        raw_bytes_estimate=123000000000,root_seed=20261008,test_cache_access=False)
    protocol['identity']=digest(protocol);atomic(ROOT/'configs/natural_route1_v1.json',protocol)
    print(json.dumps(dict(samples=len(rows),counts=protocol['counts'],anchors=anchors)),flush=True)


def capture(agent,features,value):
    import numpy as np
    import torch
    from paired_observation import modules
    head=agent.action_head;named=modules(head);step={};hidden=[];output=[];decoder=[];latents=[];means=[];logvars=[];recons=[]
    def hook(name):
        def save(module,inputs,result):
            assert name not in step;step[name]=result.detach().clone()
        return save
    handles=[module.register_forward_hook(hook(name)) for name,module in named]
    handles.append(head.model.final_layer.register_forward_hook(hook('dit_output')))
    handles.append(head.action_decoder.register_forward_hook(hook('predicted_noise')))
    original=head.p_mean_variance
    def wrapped(x,t,index,*pos,**kw):
        i=len(latents);assert int(t[0])==int(head.ddim_t[i]) and int(index[0])==i
        assert not kw.get('deterministic',False)
        step.clear();latents.append(x.detach().clone())
        result=original(x,t,index,*pos,**kw)
        means.append(result[0].detach().clone());logvars.append(result[1].detach().clone());recons.append(result[2].detach().clone())
        assert set(step)=={n for n,_ in named}|{'dit_output','predicted_noise'}
        hidden.append(torch.stack([step[n].squeeze(0) for n,_ in named]))
        output.append(step['dit_output'].squeeze(0));decoder.append(step['predicted_noise'].squeeze(0))
        return result
    head.p_mean_variance=wrapped
    try:
        batch={k:v.unsqueeze(0).cuda().float() for k,v in features.items()}
        reseed(value)
        with torch.no_grad(),torch.autocast('cuda',enabled=False):
            trajectory=agent.forward(batch)['pred_traj'].float().cpu().squeeze(0).numpy()
            # Explicit bank is reconstructed from the SAME original GPU stream, then verified.
            reseed(value)
            initial=torch.randn((1,8,3),device='cuda',dtype=torch.float32)
            noises=[torch.randn_like(initial) for _ in range(5)]
            assert torch.equal(initial,latents[0])
            for i in range(5):
                expected=means[i]+torch.exp(.5*logvars[i]).float().clamp(min=.0001)*noises[i].clamp(-1,1)
                if i<4:assert torch.equal(expected,latents[i+1])
                else:
                    expected=head.denorm_odo(expected.clamp(-1,1)).squeeze(0).float().cpu().numpy()
                    assert np.array_equal(expected,trajectory)
            arrays=dict(representations=torch.stack(hidden).float().cpu().numpy(),dit_output=torch.stack(output).float().cpu().numpy(),
                predicted_noise=torch.stack(decoder).float().cpu().numpy(),latents=torch.stack(latents).squeeze(1).cpu().numpy(),
                reconstructed_x0=torch.stack(recons).squeeze(1).cpu().numpy(),initial_noise=initial.squeeze(0).cpu().numpy(),
                step_noise=torch.stack(noises).squeeze(1).cpu().numpy(),trajectory=trajectory)
        assert len(hidden)==5 and all(np.isfinite(x).all() for x in arrays.values())
        return arrays
    finally:
        head.p_mean_variance=original
        for h in handles:h.remove()


class Moments:
    def __init__(self):self.groups={}
    def add(self,arrays,records):
        import numpy as np
        for subset in ['exploration','validation']:
            for label in ['high_quality','failure','intermediate']:
                mask=np.asarray([r['subset']==subset and r['quality']==label for r in records])
                if not mask.any():continue
                key=f'{subset}__{label}'
                y=np.asarray([r['score']['score'] for r,m in zip(records,mask) if m],dtype=np.float64)
                group=self.groups.setdefault(key,dict(n=0,sum_y=0.,sum_y2=0.))
                group['n']+=len(y);group['sum_y']+=float(y.sum());group['sum_y2']+=float(y@y)
                for field in ['representations','dit_output']:
                    x=np.moveaxis(arrays[field][mask],0,-2).astype(np.float64)
                    values={'sum':x.sum(-2),'gram':x.swapaxes(-1,-2)@x,'xy':np.einsum('...nd,n->...d',x,y,optimize=True)}
                    for name,value in values.items():
                        name=f'{field}_{name}'
                        if name not in group:group[name]=value
                        else:group[name]+=value
    def save(self,out):
        records={}
        for key,group in self.groups.items():
            path=out/f'{key}.npz';hashed=write_npz(path,**group)
            records[key]=dict(path=str(path),sha256=hashed,n=group['n'])
        atomic(out/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),groups=records))


def collect(args):
    import numpy as np
    import torch
    from worker import load_model,load_features,predict
    from representation_prepare import baseline_records
    cfg=read(ROOT/'configs/baseline.json');protocol=read(ROOT/'configs/natural_route1_v1.json')
    manifest=read(ROOT/protocol['manifest']);assert sha(ROOT/protocol['manifest'])==protocol['manifest_sha256']
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    out=ROOT/'runs'/args.run/args.phase/f'rank{args.rank:03d}';out.mkdir(parents=True,exist_ok=True)
    assert not (out/'COMPLETE.json').exists()
    atomic(out/'STATUS.json',dict(status='LOADING',time=stamp()))
    agent,runtime=load_model(cfg);atomic(out/'runtime.json',runtime)
    versions={k:p._version for k,p in agent.named_parameters()}
    if args.phase=='formal':
        assert args.world_size==32;panel=manifest[args.rank::32];anchor_records=None
    else:
        tokens=list(protocol['anchors']);candidate=manifest[3+args.rank]
        if candidate['token'] not in tokens:tokens.append(candidate['token'])
        panel=[r for r in manifest if r['token'] in tokens];anchor_records=baseline_records(set(tokens))
    moments=Moments();began=time.monotonic();completed=0;all_records=[]
    for offset in range(0,len(panel),32):
        rows=panel[offset:offset+32]
        if args.phase=='formal':
            source=ROOT/'runs'/protocol['baseline_run']/'formal'/f'rank{args.rank:03d}'/'chunks'/f'{offset:06d}.json'
            references=read(source)['records'];assert [r['token'] for r in references]==[r['token'] for r in rows]
        else:references=[anchor_records[r['token']] for r in rows]
        arrays=[];records=[]
        for row,reference in zip(rows,references):
            features,_,meta=load_features(row,cfg)
            assert meta['feature_sha256']==reference['feature_sha256']==row['feature_sha256']
            assert meta['target_sha256']==reference['target_sha256']
            result=capture(agent,features,seed(row['token']))
            assert np.array_equal(result['trajectory'],np.asarray(reference['trajectory'],dtype=np.float32)),row['token']
            if args.phase!='formal':
                assert np.array_equal(result['trajectory'],predict(agent,features,seed(row['token'])))
                repeated=capture(agent,features,seed(row['token']))
                assert all(np.array_equal(result[k],repeated[k]) for k in result)
            assert quality(reference['score']['score'])==row['quality']
            record=dict(token=row['token'],global_index=row['global_index'],seed=seed(row['token']),seed_index=0,
                session=row['session'],subset=row['subset'],quality=row['quality'],score=reference['score'],
                trajectory=reference['trajectory'],feature_sha256=meta['feature_sha256'],
                source='natural_model_S0',gt_initialization=False,exact_baseline_trajectory_replay=True,
                metric_cache=reference['metric_cache'],metric_sha256=reference['metric_sha256'],
                identity=protocol['identity'])
            arrays.append(result);records.append(record)
        arrays={k:np.stack([r[k] for r in arrays]) for k in arrays[0]}
        path=out/'chunks'/f'{offset:06d}.npz';hashed=write_npz(path,**arrays)
        atomic(path.with_suffix('.json'),dict(identity=protocol['identity'],array_sha256=hashed,array_path=str(path),records=records))
        if args.phase=='formal':moments.add(arrays,records)
        else:
            assert sha(path)==hashed
            # Exercise the full moment implementation on a tiny spatial slice.
            tile={k:(v[:,:1,:1,:1,:8] if k=='representations' else v[:,:1,:1,:8]) for k,v in arrays.items() if k in ['representations','dit_output']}
            check=Moments();check.add(tile,records)
            for key,g in check.groups.items():
                selected=[i for i,r in enumerate(records) if f'{r["subset"]}__{r["quality"]}'==key]
                x=tile['representations'][selected,0,0,0].astype(np.float64)
                assert np.array_equal(g['representations_gram'][0,0,0],x.T@x)
        all_records.extend(records);completed+=len(records)
        atomic(out/'STATUS.json',dict(status='CAPTURING',time=stamp(),completed=completed,total=len(panel),
            seconds=time.monotonic()-began,last_chunk=str(path),natural_source=True,gt_initialization=False))
        print(json.dumps(dict(rank=args.rank,completed=completed,total=len(panel),seconds=time.monotonic()-began)),flush=True)
    if args.phase=='formal':moments.save(out/'moments')
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    atomic(out/'records.json',all_records)
    receipt=dict(status='COMPLETE',time=stamp(),scenes=completed,seconds=time.monotonic()-began,identity=protocol['identity'],
        natural_source=True,gt_initialization=False,all_trajectories_exact_baseline_replay=True,parameters_unchanged=True,
        counts=dict(Counter(r['quality'] for r in all_records)))
    atomic(out/'COMPLETE.json',receipt);atomic(out/'STATUS.json',receipt)


def reduce_node(run,node):
    import numpy as np
    base=ROOT/'runs'/run;out=base/f'node{node}/moments';out.mkdir(parents=True,exist_ok=True)
    receipts=[read(base/'formal'/f'rank{rank:03d}'/'moments/COMPLETE.json') for rank in range(node*16,(node+1)*16)]
    files={}
    for key in sorted({k for r in receipts for k in r['groups']}):
        accumulator={}
        for r in receipts:
            if key not in r['groups']:continue
            src=r['groups'][key];data=retry(lambda:Path(src['path']).read_bytes())
            assert hashlib.sha256(data).hexdigest()==src['sha256']
            with np.load(io.BytesIO(data),allow_pickle=False) as z:
                for name in z.files:
                    value=z[name]
                    if name not in accumulator:accumulator[name]=value.copy()
                    else:accumulator[name]+=value
        path=out/f'{key}.npz';hashed=write_npz(path,**accumulator)
        files[key]=dict(path=str(path),sha256=hashed,n=int(accumulator['n']))
        print(json.dumps(dict(stage='reduce_moments',node=node,group=key,n=files[key]['n'])),flush=True)
    atomic(out/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),groups=files))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','collect','reduce'])
    p.add_argument('--run');p.add_argument('--phase',choices=['smoke','formal'],default='smoke');p.add_argument('--rank',type=int,default=0)
    p.add_argument('--world-size',type=int,default=1);p.add_argument('--node',type=int);args=p.parse_args()
    setup(f'natural/{args.run}/{args.phase}/{args.rank}');compatibility()
    try:
        if args.command=='prepare':prepare()
        elif args.command=='reduce':reduce_node(args.run,args.node)
        else:collect(args)
    except BaseException as error:
        if args.run:atomic(ROOT/'runs'/args.run/f'FAILED_{args.phase}_{args.rank}.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
