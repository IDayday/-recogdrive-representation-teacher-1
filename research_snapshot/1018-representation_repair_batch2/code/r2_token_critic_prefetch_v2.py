"""Candidate-outcome critic attending to full interface tokens, Base frozen.

This tests whether pooled features discard local scene information needed for
selection. Its labels are actual candidate outcomes; inference uses only current
VLM tokens and the complete candidate trajectory, with no privileged score.
"""
from r2_common import *
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor


def make_model():
    import torch
    class Critic(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.context=torch.nn.Linear(384,128);self.query=torch.nn.Linear(4,128)
            self.positions=torch.nn.Parameter(torch.randn(8,128)*.02)
            self.attention=torch.nn.ModuleList([torch.nn.MultiheadAttention(128,4,batch_first=True) for _ in range(2)])
            self.norms=torch.nn.ModuleList([torch.nn.LayerNorm(128) for _ in range(2)])
            self.head=torch.nn.Sequential(torch.nn.Linear(1024,128),torch.nn.Tanh(),torch.nn.Linear(128,7))
        def forward(self,context,trajectory):
            # context: current valid tokens; trajectory: independent full candidates
            c=self.context(context.float())[None].expand(len(trajectory),-1,-1)
            p=trajectory.float();geometry=torch.stack([p[:,:,0]/40,p[:,:,1]/10,torch.sin(p[:,:,2]),torch.cos(p[:,:,2])],-1)
            q=self.query(geometry)+self.positions[None]
            for attention,norm in zip(self.attention,self.norms):
                update,_=attention(q,c,c,need_weights=False);q=norm(q+update)
            return torch.sigmoid(self.head(q.reshape(len(p),-1)))
    return Critic().cuda().float()


@lru_cache(maxsize=12)
def block(path):
    import numpy as np
    response=read(ROOT/path)
    with np.load(ROOT/response['matrix']) as z:
        return dict(indices=np.array(z['global_indices']),scores=np.array(z['scores']),trajectory=np.array(z['trajectory']),seeds=np.array(z['seeds']))


def inner_session(session):return int(digest(dict(session=session,token_critic_calibration=20261018))[:8],16)%7==0


def run(engine,task,pool):
    import torch
    import numpy as np
    from common import reseed
    from worker import load_features
    from repair_engine import baseline_row
    from r2_cached_interfaces import from_cached
    from r2_expert_space import save_npz
    from r2_point_response import FIELDS
    held=task['heldout_fold'];source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality'])
    allowed=np.array([r['subset']=='exploration' and (held<0 or int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5!=held) for r in rows])
    train=allowed&np.array([not inner_session(r['session']) for r in rows]);cases=np.flatnonzero(train);failures=np.flatnonzero(train&(quality<.7));assert len(cases) and len(failures)
    assert task['responses'];paths=[];source_lineage=[]
    for response_path in task['responses']:
        response=read(ROOT/response_path);point=read(ROOT/response['point']);assert point['heldout_fold']==held and point['training_only']
        data=block(response_path);positions=np.flatnonzero(train[data['indices']]);assert np.all(allowed[data['indices']])
        if len(positions):paths.append((response_path,positions,data['indices'].copy(),data['scores'].shape[1],len(data['seeds'])))
        source_lineage.append(dict(path=response_path,sha256=sha(ROOT/response_path),matrix_sha256=response['matrix_sha256']))
    rng=np.random.default_rng(task['fit_seed']);schedule=[]
    for step in range(task['steps']):
        if step%4 in [0,1]:
            response_path,positions,indices,arm_count,noise_count=paths[int(rng.integers(len(paths)))]
            j=int(rng.choice(positions));arm=int(rng.integers(1,arm_count));n=int(rng.integers(noise_count))
            index=int(indices[j]);schedule.append((index,response_path,j,arm,n))
        else:schedule.append((int(rng.choice(failures if step%4==2 else cases)),None,None,None,None))
    def fetch(item):
        index,path,j,arm,n=item;features,_,_=load_features(rows[index],engine.cfg)
        if path:
            data=block(path);return features,data['trajectory'][j,[0,arm],n],data['scores'][j,[0,arm],n],int(data['seeds'][n])
        baseline=baseline_row(rows[index]);trajectory=np.asarray(baseline['trajectory'],dtype=np.float32)
        score=np.asarray([baseline['score'][f] for f in FIELDS],dtype=np.float32)
        return features,np.stack([trajectory,trajectory]),np.stack([score,score]),0
    reseed(task['fit_seed']);model=make_model();optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.001)
    destination=ROOT/'token_critic_prefetch_v2'/task['id'];destination.mkdir(parents=True,exist_ok=False);trace=[];checkpoints=[];began=time.monotonic();waiting=0.
    with ThreadPoolExecutor(max_workers=4) as reader:
        futures={j:reader.submit(fetch,schedule[j]) for j in range(min(8,len(schedule)))}
        for step,item in enumerate(schedule):
            started=time.monotonic();features,trajectory,score,noise=futures.pop(step).result();waiting+=time.monotonic()-started
            if step+8<len(schedule):futures[step+8]=reader.submit(fetch,schedule[step+8])
            index=item[0]
            with torch.no_grad():
                hidden=from_cached(engine,features,index);h=engine.prefix['interface_post'];mask,valid=engine.mask('interface_post','valid_mean');assert valid
                context=h.reshape(-1,h.shape[-1])[mask].detach();candidate=torch.as_tensor(trajectory,device='cuda');target=torch.as_tensor(score,device='cuda',dtype=torch.float32)
                if step==0:
                    native=engine.trajectory(features,hidden,seed(rows[index]['token'],noise))
                    assert np.array_equal(native.cpu().numpy(),trajectory[0]),'Critic data must use exact paired Base'
            optimizer.zero_grad(set_to_none=True);prediction=model(context,candidate)
            absolute=torch.nn.functional.mse_loss(prediction[:,0],target[:,0])
            absolute=absolute+.5*torch.nn.functional.binary_cross_entropy(prediction[:,1:3],target[:,1:3])
            absolute=absolute+.2*torch.nn.functional.binary_cross_entropy(prediction[:,3],target[:,3])+.2*torch.nn.functional.mse_loss(prediction[:,4],target[:,4])
            absolute=absolute+.05*torch.nn.functional.mse_loss(prediction[:,5:],target[:,5:])
            pair=torch.nn.functional.mse_loss(prediction[1,0]-prediction[0,0],target[1,0]-target[0,0]);loss=absolute+2*pair
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
            if step%32==0 or step+1 in task['checkpoints']:
                v=torch.stack([loss.detach(),absolute.detach(),pair.detach(),norm.detach()]).cpu().numpy();assert np.isfinite(v).all()
                trace.append(dict(step=step,index=index,candidate_source=item[1],seed_index=noise,loss=float(v[0]),absolute_loss=float(v[1]),gain_loss=float(v[2]),gradient_norm=float(v[3])))
            if step+1 in task['checkpoints']:
                path=destination/('step%05d.npz'%(step+1));hashed=save_npz(path,**{n:p.detach().cpu().numpy() for n,p in model.state_dict().items()});checkpoints.append(dict(step=step+1,path=str(path.relative_to(ROOT)),sha256=hashed))
    engine.verify_engine();record=dict(status='CRITIC_TRAINED_NOT_POLICY_VALIDATED',time=stamp(),task=task,heldout_fold=held,fit_seed=task['fit_seed'],
        checkpoints=checkpoints,trace=trace,seconds=time.monotonic()-began,input_wait_seconds=waiting,
        prefetch_readers=4,prefetch_depth=8,training_rows=int(train.sum()),calibration_sessions_excluded=True,source_responses=source_lineage,
        full_valid_interface_tokens=True,Base_frozen=True,true_outcome_labels=True,PDMS_GT_not_inference_features=True,
        validation_fitted=False,test_accessed=False)
    atomic(destination/'TRAINING.json',record);return dict(path=str((destination/'TRAINING.json').relative_to(ROOT)),seconds=record['seconds'],checkpoints=checkpoints)


@lru_cache(maxsize=12)
def load(path,expected):
    import numpy as np
    import torch
    assert sha(ROOT/path)==expected;model=make_model()
    with np.load(ROOT/path) as z:model.load_state_dict({n:torch.as_tensor(np.array(z[n]),device='cuda') for n in z.files})
    model.eval()
    for p in model.parameters():p.requires_grad_(False)
    return model
