"""One visible GPU per torchrun rank, using the frozen original training program."""
from __future__ import annotations
import argparse
import datetime
import json
import os
from pathlib import Path
import traceback
from continuation.layout import BATCHES,Runtime,sha,write_json

def execute(a):
    rank=int(os.environ['RANK']);world=int(os.environ['WORLD_SIZE']);local=int(os.environ['LOCAL_RANK'])
    devices=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    if len(devices)!=world or not all(devices):raise ValueError('Expose exactly the requested local devices')
    os.environ['CUDA_VISIBLE_DEVICES']=devices[local]
    os.environ['RECOGDRIVE_CONTINUATION_PATHS']=str(Path(a.paths).resolve())
    os.environ['RECOGDRIVE_CONTINUATION_WORKSPACE']=str(Path(a.workspace).resolve())
    runtime=Runtime(a.paths,a.workspace).bootstrap();root=runtime.workspace/BATCHES[3]
    config=runtime.read(a.config);config_sha=sha(a.config)
    if world!=config['world_size']:raise ValueError('torchrun topology differs from the configuration')
    import torch
    import torch.distributed as dist
    from continuation.identity import backend,verified_models
    verified_models(runtime)
    protocol=root/'runs/full_context_replay_v1/PORTABLE_PROTOCOL.json'
    teacher_environment=runtime.read(protocol).get('environment')if protocol.exists()else None
    from continuation.dataset import install
    install(runtime)
    from continuation.runtime_workers import initialize_score
    import d4_development_eval_v3
    d4_development_eval_v3.initialize_score=initialize_score
    from continuation.development import evaluate
    d4_development_eval_v3.evaluate=evaluate
    if a.mode=='preflight':
        from d4_student_v1 import Student,losses
        from d4_dataset_v2 import TeacherDataset
        from d4_distributed_v1 import wrap
        dist.init_process_group('nccl',rank=rank,world_size=world,timeout=datetime.timedelta(minutes=15))
        student=Student(config);model,proof=wrap(student)
        indices=runtime.read(config['train_indices']);rows=runtime.read(config['scene_manifest'])
        improved=[i for i in indices if rows[i]['pool']=='I'];scene=improved[rank%len(improved)]
        data=TeacherDataset([scene],config['scene_manifest'],config['scene_manifest_sha256'])[0]
        outputs=model(data['features'],data['token'],data['noise_index'],trajectory=config['group']!='H')
        if not torch.equal(outputs['input_ids'][0],data['target']['input_ids'].cuda()):raise ValueError('Tokenizer/input IDs changed')
        if not torch.equal(outputs['attention_mask'][0],data['target']['attention_mask'].cuda()):raise ValueError('Attention mask changed')
        lh,lt=losses(outputs,data['target'],data['noise_index'])
        loss=config['lambda_H']*lh
        if lt is not None:loss=loss+config['lambda_T']*lt
        loss.backward();student.verify_frozen()
        gradients=[p.grad for p in student.parameters()if p.requires_grad and p.grad is not None]
        if not gradients or not all(torch.isfinite(v).all()for v in gradients)or not any(bool(v.abs().sum()>0)for v in gradients):
            raise ValueError('Missing, zero or nonfinite gradients on an improved training scene')
        record=dict(status='PASS_ACTUAL_TARGET_DDP_FORWARD_BACKWARD',rank=rank,world_size=world,
            configuration_sha256=config_sha,device=torch.cuda.get_device_name(0),torch_version=torch.__version__,
            environment=backend(),teacher_environment=teacher_environment,
            loss=float(loss.detach()),source_parameter_broadcast=proof,teacher_full_padding_retained=True)
        write_json(root/'runs'/config['run_id']/'portable_preflight'/f'rank{rank:02d}.json',record)
        dist.barrier()
        if rank==0:
            write_json(root/'provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V2.json',dict(
                status='PASS_ACTUAL_PORTABLE_TARGET_DDP_PREFLIGHT',configuration_sha256=config_sha,
                world_size=world,source_PPU_acceptance_not_substituted=True))
        dist.barrier();dist.destroy_process_group();return
    for other in range(world):
        proof=runtime.read(root/'runs'/config['run_id']/'portable_preflight'/f'rank{other:02d}.json')
        if proof['status']!='PASS_ACTUAL_TARGET_DDP_FORWARD_BACKWARD' or proof['configuration_sha256']!=config_sha or proof.get('environment')!=backend():
            raise ValueError('Target multi-GPU preflight has not passed')
    # The source PPU CUDA RNG byte format may differ from NVIDIA's generator.
    # Per-scene action noise is already explicitly seeded/forked by the original code.
    original_load=torch.load
    resume=Path(a.resume).resolve()if a.resume else None
    def load(path,*args,**kwargs):
        state=original_load(path,*args,**kwargs)
        if resume is not None and isinstance(path,(str,Path)) and Path(path).resolve()==resume and state.get('portable_migration',{}).get('native_cuda_rng_reset_required'):
            torch.cuda.manual_seed(config['initialization_seed']+rank)
            native=torch.cuda.get_rng_state(0)
            state['random_states'][rank]['cuda']=native
            write_json(root/'runs'/config['run_id']/'portable_preflight'/f'cuda_rng_migration_rank{rank:02d}.json',
                dict(status='EXPLICIT_TARGET_NATIVE_CUDA_RNG_INITIALIZATION',rank=rank,
                    source_checkpoint_sha256=sha(resume),bitwise_resume_claimed=False))
        return state
    torch.load=load
    try:
        import d4_train_v4
        d4_train_v4.main(argparse.Namespace(config=a.config,run=config['run_id'],rank=rank,world_size=world,resume=a.resume,stop_after_epoch=0))
    finally:torch.load=original_load

def main():
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--config',required=True);p.add_argument('--resume');p.add_argument('--mode',choices=['preflight','train'],required=True)
    a=p.parse_args()
    try:execute(a)
    except BaseException:
        root=Path(a.workspace)/BATCHES[3]
        write_json(root/'portable_failures'/f"{a.mode}_rank{os.environ.get('RANK','unknown')}.json",dict(status='FAILED',traceback=traceback.format_exc()))
        raise

if __name__=='__main__':main()
