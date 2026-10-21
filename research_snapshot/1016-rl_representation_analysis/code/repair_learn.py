"""Natural S0 input states -> same-scene high-quality reference states, with actual success replay."""
from common import *
import numpy as np
from paired_observation import save_arrays

def main():
    setup('repair/natural_learn');compatibility()
    import torch
    torch.set_num_threads(1)
    root=ROOT/'repair_v1';nat=ROOT/'analysis/natural_route1_v1';pair=ROOT/'analysis/observation_v1/cache'
    meta=read(nat/'metadata.json');index={r['token']:i for i,r in enumerate(meta)}
    paired=read(pair/'metadata.json');q=np.load(pair/'scores.npy')[0]
    train=np.array([r['subset']=='exploration' for r in paired]);mask=train&(((q[:,0]<.7)&(q[:,1]>.9))|((q[:,1]<.7)&(q[:,0]>.9)))
    ids=np.flatnonzero(mask);natural_ids=[index[paired[i]['token']] for i in ids];branches=np.argmax(q[ids],axis=1)
    scores=np.load(nat/'scores.npy');replay=[]
    for label,n in [('high_quality',6000),('intermediate',2000)]:
        replay+=sorted([i for i,r in enumerate(meta) if r['subset']=='exploration' and quality(float(scores[i]))==label],key=lambda i:digest(dict(token=meta[i]['token'],replay=20261016)))[:n]
    coords=np.load(nat/'coordinates_hidden.npy',mmap_mode='r');px=np.load(pair/'hidden_P0.npy',mmap_mode='r')
    results=[]
    for layer in [6,10,17]:
        arrays={};history=[]
        with np.load(root/'fits'/f's4_l{layer}_k8.npz') as fits:
            for tok in range(8):
                prefix=f'n_{tok}_';b=fits[prefix+'b'];c=fits[prefix+'center'];scale=fits[prefix+'scale']
                native=np.array(coords[natural_ids,4,layer,tok,8:16],dtype=np.float64)
                high=(np.array(px[ids,branches,layer,tok],dtype=np.float64)-c)@b
                success=np.array(coords[replay,4,layer,tok,8:16],dtype=np.float64)
                x=np.concatenate([native,success,high]);target=np.concatenate([high-native,np.zeros_like(success),np.zeros_like(high)])
                # Class weights prevent ordinary cases numerically erasing the repair supervision.
                weight=np.r_[np.ones(len(native)),np.full(len(success),len(native)/len(success)),np.ones(len(high))]
                mean=x.mean(0);std=np.maximum(x.std(0),1e-5);xx=(x-mean)/std;design=np.c_[xx,np.ones(len(xx))]
                ridge=np.linalg.solve(design.T@(weight[:,None]*design)+.1*weight.sum()*np.eye(9),design.T@(weight[:,None]*target))
                arrays.update({prefix+'reg':ridge,prefix+'zm':mean,prefix+'zs':std,prefix+'local_low':native,prefix+'local_delta':high-native})
                torch.manual_seed(20261016+100*layer+tok)
                net=torch.nn.Sequential(torch.nn.Linear(8,32),torch.nn.Tanh(),torch.nn.Linear(32,8))
                torch.nn.init.zeros_(net[-1].weight);torch.nn.init.zeros_(net[-1].bias)
                opt=torch.optim.AdamW(net.parameters(),lr=.003,weight_decay=.01)
                xt=torch.tensor(xx,dtype=torch.float32);yt=torch.tensor(target/scale,dtype=torch.float32);wt=torch.tensor(weight,dtype=torch.float32)
                def loss():
                    pred=net(xt);return ((pred-yt).square().mean(1)*wt).sum()/wt.sum()+.01*(pred.square().mean(1)*wt).sum()/wt.sum()
                initial=float(loss().detach())
                for update in range(400):opt.zero_grad();value=loss();value.backward();opt.step()
                final=float(loss().detach());assert final<=initial+1e-6
                for name,value in net.state_dict().items():arrays[prefix+'mlp_'+name]=value.detach().numpy()
                history.append(dict(token=tok,initial_loss=initial,final_loss=final,updates=400))
        path=root/'fits'/f'natural_learn_l{layer}_k8.npz';assert not path.exists();save_arrays(path,**arrays)
        receipt=dict(status='COMPLETE',time=stamp(),layer=layer,natural_failure_inputs=len(ids),natural_success_and_middle_replay=len(replay),
            high_identity_pairs=len(high),fit_subset='exploration only',target='same-scene final PDMS>90 reference projected into natural basis',
            quality_gate_after_denoising=True,base_weights_changed=False,seed=20261016,updates=history,sha256=sha(path))
        atomic(path.with_suffix('.json'),receipt);results.append(receipt)
        print(json.dumps(dict(layer=layer,pairs=len(ids),replay=len(replay))),flush=True)
    atomic(root/'NATURAL_LEARN_READY.json',dict(status='COMPLETE',time=stamp(),fits=results))

if __name__=='__main__':main()
