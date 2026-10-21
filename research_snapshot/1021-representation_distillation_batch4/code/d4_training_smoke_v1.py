"""True Base replay, differentiable H/T/HT, frozen-weight and small-fit checks."""
from d4_common import *
import traceback


def main():
    setup('training_smoke_v1');compatibility()
    import numpy as np
    import torch
    import psutil
    import socket
    from vlm_core import raw_features
    from d4_student_v1 import Student,losses
    config=dict(initialization_seed=2026102101,lora_rank=16,lora_alpha=32,lora_dropout=0.,gradient_checkpointing=True,
        lora_learning_rate=5e-5,projection_learning_rate=1e-4,optimizer='AdamW',weight_decay=0.,gradient_clip_norm=1.)
    free,total=torch.cuda.mem_get_info()
    assert torch.cuda.device_count()==1 and free>70*(1<<30) and psutil.virtual_memory().available>30*(1<<30)
    atomic(ROOT/'provenance/DSW_TRAINING_PREFLIGHT_V1.json',dict(time=stamp(),hostname=socket.gethostname(),
        actual_devices=1,device_name=torch.cuda.get_device_name(0),device_free_bytes=free,host_available_bytes=psutil.virtual_memory().available))
    scenes=read(ROOT/'manifests/R2_SCENES_V1.json');indices=read(ROOT/'manifests/SMOKE_INDICES_V1.json')
    student=Student(config);atomic(ROOT/'provenance/TRAINABLE_MODULES_SMOKE_V1.json',student.module_manifest)
    examples=[];replays=[]
    for index in indices:
        row=scenes[index];features=raw_features(row)
        record=read(ROOT/'runs/teacher_replay_smoke_v1/cases'/row['token']/'RESULT.json')
        with np.load(ROOT/record['arrays']['path'],allow_pickle=False) as z:target={k:np.array(z[k]) for k in z.files}
        old=read(B3/row['source_record']);base={r['seed_index']:r for r in old['records'] if r['arm']=='Base'}
        with torch.no_grad():
            for j in range(5):
                output=student(features,row['token'],j,trajectory=True)
                assert np.array_equal(output['prediction'][0].float().cpu().numpy(),np.asarray(base[j]['trajectory'],dtype=np.float32))
                assert np.array_equal(output['input_ids'][0].cpu().numpy(),target['input_ids'])
                assert np.array_equal(output['attention_mask'][0].cpu().numpy(),target['attention_mask'])
                if row['pool']=='P':assert np.array_equal(output['interface'][0].float().cpu().numpy(),target['teacher_interface'])
        replays.append(dict(global_index=index,token=row['token'],pool=row['pool'],Base_all_five_trajectories_exact=True,
            full_tokens=len(target['input_ids']),padding_tokens=int((target['attention_mask']==0).sum())))
        examples.append((row,features,target))
    student.verify_frozen()
    row,features,target=next(e for e in examples if e[0]['pool']=='I' and e[0]['subset']=='exploration')
    output=student(features,row['token'],0,trajectory=True);lh,lt=losses(output,target,0)
    gh=torch.autograd.grad(lh,output['interface'],retain_graph=True)[0]
    gt=torch.autograd.grad(lt,output['interface'],retain_graph=True)[0]
    nh=float(gh.norm());nt=float(gt.norm());assert nh>0 and nt>0 and np.isfinite([nh,nt]).all()
    ratio=nh/nt;del output,lh,lt,gh,gt
    initial={n:p.detach().clone() for n,p in student.named_parameters() if p.requires_grad};results={}
    for group in ['H','T','HT']:
        with torch.no_grad():
            for name,p in student.named_parameters():
                if p.requires_grad:p.copy_(initial[name])
        optimizer=torch.optim.AdamW(student.optimizer_groups(),weight_decay=0.)
        history=[];gradient_groups=None;began=time.monotonic()
        for step in range(13):
            optimizer.zero_grad(set_to_none=True)
            output=student(features,row['token'],0,trajectory=group!='H');lh,lt=losses(output,target,0)
            loss=lh if group=='H' else lt if group=='T' else lh+ratio*lt
            assert torch.isfinite(loss)
            if step in [0,4,8,12]:history.append(dict(step=step,loss=float(loss.detach()),H=float(lh.detach()),T=None if lt is None else float(lt.detach())))
            if step==12:break
            loss.backward();grads={}
            for name,p in student.named_parameters():
                if not p.requires_grad or p.grad is None:continue
                assert torch.isfinite(p.grad).all(),name
                category='vision_lora' if '.vision_model.' in name else 'language_lora' if '.language_model.' in name else 'visual_language_projection' if '.mlp1.' in name else 'interface_projection'
                grads[category]=grads.get(category,0.)+float(p.grad.detach().square().sum())
            if step==0:
                assert set(grads)=={'vision_lora','language_lora','visual_language_projection','interface_projection'}
                assert all(v>0 for v in grads.values()),grads;gradient_groups=grads
            torch.nn.utils.clip_grad_norm_([p for p in student.parameters() if p.requires_grad],1.)
            optimizer.step();student.verify_frozen()
        assert history[-1]['loss']<history[0]['loss'],(group,history)
        results[group]=dict(history=history,first_gradient_squared_norm_by_group=gradient_groups,seconds=time.monotonic()-began)
        del output,lh,lt,loss,optimizer
    student.verify_frozen()
    proof=dict(status='PASS_NATIVE_REPLAY_AND_GRADIENT_AND_SMALL_FIT',time=stamp(),config=config,replays=replays,
        calibration_example_index=row['global_index'],initial_interface_H_gradient_norm=nh,initial_interface_T_gradient_norm=nt,
        single_example_HT_lambda_T=ratio,calibration_not_final_training_weight=True,groups=results,
        frozen_original_parameters_unchanged=True,native_sampling_differentiated_without_inference_cache=True,GT_used=False,
        peak_process_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),training_smoke_not_formal_result=True)
    atomic(ROOT/'provenance/TRAINING_SMOKE_V1.json',proof)
    print(json.dumps(dict(status=proof['status'],groups={k:v['history'] for k,v in results.items()},peak_GB=proof['peak_process_cuda_allocated_bytes']/1e9)),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'provenance/TRAINING_SMOKE_FAILED_V1.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
