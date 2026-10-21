"""Map a committed optimizer boundary to a different single-node rank count.

Model/optimizer tensors and the global sample stream are preserved. Distributed
reduction order and PPU/CUDA RNG algorithms cannot be made bitwise identical.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
from continuation.layout import BATCHES,sha,write_json

def exposure_for_ranks(config,indices,scenes,epoch,next_micro,world_size):
    import numpy as np
    batch=config['global_batch_size'];padded=((len(indices)+batch-1)//batch)*batch
    counts=[dict(exposure=0,pools={}) for _ in range(world_size)]
    for e in range(epoch+1):
        if e==epoch and next_micro==0:break
        order=np.asarray(indices,dtype=np.int64).copy()
        np.random.default_rng(config['data_seed']+e).shuffle(order)
        if padded>len(order):order=np.concatenate([order,order[:padded-len(order)]])
        for rank in range(world_size):
            local=order[rank::world_size]
            if e==epoch:local=local[:next_micro]
            counts[rank]['exposure']+=len(local)
            for index in local:
                pool=scenes[int(index)]['pool'];counts[rank]['pools'][pool]=counts[rank]['pools'].get(pool,0)+1
    return counts

def remap_state(state,config,config_sha,indices,scenes,world_size):
    old_world=len(state['random_states']);old_micro=state['next_micro']
    if config['global_batch_size']%world_size:raise ValueError('Rank count must divide the unchanged global batch')
    if old_micro%(config['global_batch_size']//old_world):raise ValueError('Only committed optimizer boundaries may be migrated')
    if old_micro*old_world%world_size:raise ValueError('Data position cannot be mapped exactly')
    next_micro=old_micro*old_world//world_size
    counts=exposure_for_ranks(config,indices,scenes,state['epoch'],next_micro,world_size)
    if sum(x['exposure'] for x in counts)!=state['global_step']*config['global_batch_size']:
        raise ValueError('Global exposure does not agree with the saved optimizer step')
    result=dict(state,configuration=config,configuration_sha256=config_sha,next_micro=next_micro)
    result['random_states']=[dict(state['random_states'][rank%old_world],rank=rank,
        exposure=counts[rank]['exposure'],pools=counts[rank]['pools']) for rank in range(world_size)]
    result['portable_migration']=dict(source_world_size=old_world,target_world_size=world_size,
        original_next_micro=old_micro,target_next_micro=next_micro,
        optimizer_and_trainable_tensors_unchanged=True,global_sample_prefix_unchanged=True,
        native_cuda_rng_reset_required=True,bitwise_resume_claimed=False)
    return result

def main(a):
    import torch
    workspace=Path(a.workspace).resolve();root=workspace/BATCHES[3]
    capture=json.loads((workspace/'PORTABLE_SNAPSHOT.json').read_text())['groups'][a.group]
    original=root/'configs/distillation_main_v4'/(a.group+'.json')
    if sha(original)!=capture['original_config_sha256']:raise ValueError('Original configuration changed')
    config=json.loads(original.read_text())
    run=a.run or ('distillation_a800_8gpu_'+a.group)
    config.update(run_id=run,world_size=a.world_size,devices=list(range(a.world_size)),node='portable',job=None,
        portable_migration=dict(original_configuration_sha256=sha(original),original_world_size=16,
            source_backend='PPU-ZW810E',target_backend='NVIDIA CUDA',bitwise_resume_claimed=False))
    config_path=root/'configs/portable'/(run+'.json')
    if config_path.exists() and json.loads(config_path.read_text())!=config:raise ValueError('Use a new run ID')
    write_json(config_path,config);config_sha=sha(config_path)
    indices=json.loads((root/'manifests/TRAIN_INDICES_V2.json').read_text())
    scenes=json.loads((root/'manifests/R2_TRAINING_SCENES_V2.json').read_text())
    run_dir=root/'runs'/run;run_dir.mkdir(parents=True,exist_ok=True)
    best_ref=capture['best_development']['checkpoint'];best_source=root/best_ref['path']
    if sha(best_source)!=best_ref['sha256']:raise ValueError('Original best checkpoint changed')
    best_state=torch.load(best_source,map_location='cpu',weights_only=False)
    best_state=remap_state(best_state,config,config_sha,indices,scenes,a.world_size)
    best_state['best_development']=None
    best_path=run_dir/'imported/best_source.pt';best_path.parent.mkdir(parents=True,exist_ok=True)
    torch.save(best_state,best_path);del best_state
    best=dict(capture['best_development'],checkpoint=dict(path=str(best_path.relative_to(root)),sha256=sha(best_path),
        global_step=best_ref['global_step'],epoch=best_ref['epoch'],next_micro=0),
        historical_source_backend='PPU; reevaluate on target for same-backend checkpoint selection')
    source=root/capture['latest']['path']
    if sha(source)!=capture['latest']['sha256']:raise ValueError('Snapshot latest checkpoint changed')
    state=torch.load(source,map_location='cpu',weights_only=False)
    if state['configuration_sha256']!=capture['original_config_sha256']:raise ValueError('Checkpoint configuration does not match')
    state=remap_state(state,config,config_sha,indices,scenes,a.world_size);state['best_development']=best
    dest=run_dir/'imported/resume.pt';torch.save(state,dest)
    write_json(run_dir/'BEST_DEVELOPMENT.json',dict(status='HISTORICAL_BEST_IMPORTED_NOT_REEVALUATED_ON_TARGET',
        configuration_sha256=config_sha,**best))
    proof=dict(status='MIGRATED_OPTIMIZER_BOUNDARY_NOT_BITWISE_CROSS_BACKEND_RESUME',group=a.group,
        source_checkpoint_sha256=sha(source),source_configuration_sha256=capture['original_config_sha256'],
        checkpoint=str(dest),checkpoint_sha256=sha(dest),configuration=str(config_path),configuration_sha256=config_sha,
        global_step=state['global_step'],epoch=state['epoch'],migration=state['portable_migration'])
    write_json(run_dir/'MIGRATION.json',proof);print(json.dumps(proof,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--group',choices=['H','T','HT'],required=True)
    p.add_argument('--world-size',type=int,default=8);p.add_argument('--run');main(p.parse_args())
