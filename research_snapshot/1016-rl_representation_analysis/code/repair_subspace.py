"""Matched fixed/learnable rank-16 subspaces; exploration P0 only, frozen Base."""
from common import *
import numpy as np
from paired_observation import save_arrays

def main():
    setup('repair/subspace');compatibility()
    import torch
    torch.set_num_threads(1)
    from repair_prepare import fit_site
    from observation_analysis import paired_arrays,endpoint_mask
    layer=6;k=16;root=ROOT/'repair_v1';cache=ROOT/'analysis/observation_v1/cache'
    target_path=root/'fits'/f'natural_learn_l{layer}_k{k}.npz'
    assert not target_path.exists(), 'Never overwrite fitted parameters'
    basefit=root/'fits'/f's4_l{layer}_k{k}.npz'
    if not basefit.exists():fit_site(layer,4,k)
    metadata=read(cache/'metadata.json');quality=np.load(cache/'scores.npy')[0]
    mask=np.array([r['subset']=='exploration' for r in metadata])&endpoint_mask(quality)
    hidden=np.load(cache/'hidden_P0.npy',mmap_mode='r')
    output={};history=[]
    with np.load(basefit) as fit:
        for token in range(8):
            high,low=paired_arrays(np.array(hidden[:,:,layer,token],dtype=np.float64),quality,mask)
            x=np.r_[low,high];y=np.r_[high-low,np.zeros_like(high)]
            center=x.mean(0);b0=fit[f'p_{token}_b']
            # QR is shared by both variants, including its sign convention.
            initial_basis=torch.linalg.qr(torch.tensor(b0,dtype=torch.float32),mode='reduced').Q.detach()
            initial_projection=(x-center)@initial_basis.numpy()
            input_scale=np.maximum(initial_projection.std(0),1e-4)
            output_scale=np.maximum((y@initial_basis.numpy()).std(0),1e-4)
            xt=torch.tensor(x-center,dtype=torch.float32);yt=torch.tensor(y,dtype=torch.float32)
            xs=torch.tensor(input_scale,dtype=torch.float32);ys=torch.tensor(output_scale,dtype=torch.float32)
            normalizer=max(float(np.mean(y*y)),1e-6)
            for source,learn_basis in [('fs',False),('ls',True)]:
                torch.manual_seed(20261016+layer*100+token)
                net=torch.nn.Sequential(torch.nn.Linear(k,32),torch.nn.Tanh(),torch.nn.Linear(32,k))
                torch.nn.init.zeros_(net[-1].weight);torch.nn.init.zeros_(net[-1].bias)
                raw=torch.nn.Parameter(initial_basis.clone(),requires_grad=learn_basis)
                groups=[dict(params=net.parameters(),lr=.003)]
                if learn_basis:groups.append(dict(params=[raw],lr=.001,weight_decay=0.))
                optimizer=torch.optim.AdamW(groups,weight_decay=.01)
                def evaluate():
                    if learn_basis:
                        q,r=torch.linalg.qr(raw,mode='reduced')
                        # Fix QR's arbitrary column signs, keeping a continuous local chart.
                        signs=torch.where(torch.diag(r)>=0,1.,-1.)
                        b=q*signs
                    else:b=raw
                    pred=(net((xt@b)/xs)*ys)@b.T
                    mse=(pred-yt).square().mean()/normalizer
                    drift=1-(b.T@initial_basis).square().sum()/k
                    loss=mse+.01*pred.square().mean()/normalizer+.01*drift
                    return loss,mse,b
                start_loss,start_mse,_=evaluate();initial=float(start_loss.detach());initial_mse=float(start_mse.detach())
                gradient_norm=0.;best_loss=initial;best_update=0
                best_net={n:v.detach().clone() for n,v in net.state_dict().items()};best_raw=raw.detach().clone()
                for update in range(400):
                    optimizer.zero_grad();loss,_,_=evaluate();loss.backward()
                    if learn_basis:gradient_norm=max(gradient_norm,float(raw.grad.norm()))
                    optimizer.step()
                    current,_,_=evaluate()
                    if float(current.detach())<best_loss:
                        best_loss=float(current.detach());best_update=update+1
                        best_net={n:v.detach().clone() for n,v in net.state_dict().items()};best_raw=raw.detach().clone()
                net.load_state_dict(best_net)
                with torch.no_grad():raw.copy_(best_raw)
                loss,mse,b=evaluate();basis=b.detach().numpy()
                assert float(loss)<=initial+1e-5
                p=f'{source}_{token}_';high_z=(high-center)@basis;low_z=(low-center)@basis
                output.update({p+'b':basis,p+'center':center,p+'mh':high_z.mean(0),p+'ml':low_z.mean(0),
                    p+'scale':output_scale,p+'zm':np.zeros(k),p+'zs':input_scale})
                for name,value in net.state_dict().items():output[p+'mlp_'+name]=value.detach().numpy()
                singular=np.linalg.svd(initial_basis.numpy().T@basis,compute_uv=False)
                history.append(dict(token=token,source=source,learn_basis=learn_basis,initial_loss=initial,final_loss=float(loss.detach()),
                    initial_mse=initial_mse,final_mse=float(mse.detach()),updates=400,selected_update=best_update,basis_gradient_max=gradient_norm,
                    principal_angles_degrees=np.degrees(np.arccos(np.clip(singular,-1,1))).tolist(),seed=20261016+layer*100+token))
            print(json.dumps(dict(token=token,complete=True)),flush=True)
    save_arrays(target_path,**output)
    receipt=dict(status='COMPLETE',time=stamp(),layer=layer,k=k,sha256=sha(target_path),
        fit_subset='exploration P0 only',pairs=len(high),high_identity=len(high),natural_success_replay=0,
        overlay_filename='Legacy runtime loading convention; sources fs/ls are paired, not natural.',
        compared='identical initialization, pairs, objective, network, updates; fixed versus learnable orthonormal basis',
        base_parameters_updated=False,history=history,code_sha256=sha(ROOT/'code/repair_subspace.py'))
    atomic(target_path.with_suffix('.json'),receipt)
    arms=[]
    for source in ['fs','ls']:
        for alpha in [.25,.5,1.]:
            arm=dict(method='mlp',source=source,layer=layer,steps=[4],k=k,alpha=alpha,tokens=list(range(8)),cap=.05,gate='none',
                trainable_subspace=source=='ls',matched_subspace_control=True)
            arm['id']=f'mlp_{source}_l{layer}_k{k}_a{alpha}_'+digest(arm)[:8];arms.append(arm)
    atomic(root/'subspace_validation_arms.json',arms)
    atomic(root/'SUBSPACE_FITS_READY.json',receipt)

if __name__=='__main__':main()
