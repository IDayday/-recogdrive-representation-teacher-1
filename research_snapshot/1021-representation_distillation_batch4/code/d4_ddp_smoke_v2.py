"""Actual node-wide gradient/collective and exact-initial-Base smoke."""
from d4_common import *
import argparse
import datetime
import traceback


def main(a):
    setup('ddp_smoke/'+a.node+'/rank%02d'%a.rank);compatibility()
    import numpy as np
    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel as DDP
    from d4_student_v1 import Student,losses
    from vlm_core import raw_features
    assert torch.cuda.device_count()==1 and torch.cuda.mem_get_info()[0]>12*(1<<30)
    dist.init_process_group('nccl',rank=a.rank,world_size=a.world_size,timeout=datetime.timedelta(minutes=20))
    config=dict(initialization_seed=2026102101,lora_rank=16,lora_alpha=32,lora_dropout=0.,gradient_checkpointing=True,
        lora_learning_rate=5e-5,projection_learning_rate=1e-4,optimizer='AdamW',weight_decay=0.,gradient_clip_norm=1.)
    from d4_distributed_v1 import wrap
    student=Student(config);model,broadcast_proof=wrap(student)
    rows=read(ROOT/'manifests/R2_TRAINING_SCENES_V2.json');indices=[i for i in read(ROOT/'manifests/SMOKE_INDICES_V1.json') if rows[i]['subset']=='exploration'];assert len(indices)>=2 and all(rows[i]['pool'] in ['I','P'] for i in indices)
    optimizer=torch.optim.AdamW(student.optimizer_groups(),weight_decay=0.);history=[]
    weight=read(ROOT/'configs/LOSS_CALIBRATION_V1.json')['lambda_T']
    for step in range(3):
        row=rows[indices[(a.rank+step)%len(indices)]];features=raw_features(row);j=(a.rank+step)%5
        record=read(ROOT/'runs/teacher_replay_smoke_v1/cases'/row['token']/'RESULT.json')
        with np.load(ROOT/record['arrays']['path'],allow_pickle=False) as z:target={k:np.array(z[k]) for k in z.files}
        if step==0:
            with torch.no_grad():out=student(features,row['token'],j,trajectory=True)
            old=read(B3/row['source_record']);base=next(r for r in old['records'] if r['arm']=='Base' and r['seed_index']==j)
            assert np.array_equal(out['prediction'][0].cpu().numpy(),np.asarray(base['trajectory'],dtype=np.float32))
        optimizer.zero_grad(set_to_none=True)
        out=model(features,row['token'],j,trajectory=a.group!='H');lh,lt=losses(out,target,j)
        loss=lh if a.group=='H' else lt if a.group=='T' else lh+weight*lt
        assert torch.isfinite(loss);loss.backward()
        torch.nn.utils.clip_grad_norm_([p for p in student.parameters() if p.requires_grad],1.,error_if_nonfinite=True)
        optimizer.step();student.verify_frozen();history.append(float(loss.detach()))
    hashed=hashlib.sha256()
    for name,p in student.named_parameters():
        if p.requires_grad:hashed.update(name.encode());hashed.update(p.detach().cpu().numpy().tobytes())
    identity=hashed.hexdigest();all_hashes=[None]*a.world_size;dist.all_gather_object(all_hashes,identity)
    assert len(set(all_hashes))==1
    proof=dict(status='PASS_REAL_NODE_DDP_GRADIENT_AND_BASE_REPLAY',time=stamp(),rank=a.rank,world_size=a.world_size,node=a.node,group=a.group,
        history=history,all_rank_trainable_weights_sha256=identity,trainable_parameters=student.module_manifest['trainable_parameters'],
        frozen_original_parameters_unchanged=True,initial_native_Base_trajectory_exact=True,peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
        backend=dist.get_backend(),device=torch.cuda.get_device_name(0),config=config,HT_lambda_T=weight,broadcast_value_verification=broadcast_proof)
    atomic(ROOT/'runs/ddp_smoke_v2'/a.node/('rank%02d_PASS.json'%a.rank),proof)
    dist.barrier()
    if a.rank==0:atomic(ROOT/'runs/ddp_smoke_v2'/a.node/'ALL_RANKS_PASS.json',dict(status='ALL_ACTUAL_DDP_RANKS_PASS_REQUIRES_AGENT_REVIEW',time=stamp(),world_size=a.world_size,group=a.group,trainable_weights_sha256=identity))
    dist.destroy_process_group();print(json.dumps(dict(status=proof['status'],rank=a.rank,group=a.group)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rank',type=int,required=True);p.add_argument('--world-size',type=int,required=True)
    p.add_argument('--node',required=True);p.add_argument('--group',choices=['H','T','HT'],required=True);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/ddp_smoke_v2'/a.node/('rank%02d_FAILED.json'%a.rank),dict(status='FAILED',time=stamp(),rank=a.rank,group=a.group,error=repr(error),traceback=traceback.format_exc()));raise
