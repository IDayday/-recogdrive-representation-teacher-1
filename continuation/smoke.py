"""One-device H/T/HT autograd check against an actual regenerated teacher.

No optimizer step is taken. This checks the local model/library combination;
the separate eight-rank preflight is still required before formal training.
"""
import argparse
from pathlib import Path
from continuation.layout import BATCHES, Runtime, write_json


def main(a):
    runtime = Runtime(a.paths, a.workspace).bootstrap()
    root = runtime.workspace / BATCHES[3]
    from continuation.identity import backend, verified_models
    verified_models(runtime)
    from continuation.dataset import install
    install(runtime)
    import torch
    from d4_dataset_v2 import TeacherDataset
    from d4_student_v1 import Student, losses
    configs = {g: runtime.read(root / 'configs/distillation_main_v4' / (g + '.json'))
               for g in ['H', 'T', 'HT']}
    config = configs['HT']
    data = TeacherDataset([a.index], config['scene_manifest'], config['scene_manifest_sha256'])[0]
    if data['pool'] != 'I':
        raise ValueError('Use an improved training scene to exercise nonzero repair gradients')
    student = Student(config)
    results = []
    for group, current in configs.items():
        student.zero_grad(set_to_none=True)
        outputs = student(data['features'], data['token'], data['noise_index'], trajectory=group != 'H')
        if not torch.equal(outputs['input_ids'][0], data['target']['input_ids'].cuda()):
            raise ValueError('Input IDs differ from the teacher')
        if not torch.equal(outputs['attention_mask'][0], data['target']['attention_mask'].cuda()):
            raise ValueError('Attention masks differ from the teacher')
        lh, lt = losses(outputs, data['target'], data['noise_index'])
        loss = current['lambda_H'] * lh
        if lt is not None:
            loss = loss + current['lambda_T'] * lt
        loss.backward()
        gradients = [p.grad for p in student.parameters() if p.requires_grad and p.grad is not None]
        if not gradients or not all(bool(torch.isfinite(v).all()) for v in gradients):
            raise ValueError('Missing or nonfinite gradients')
        if not any(bool(v.abs().sum() > 0) for v in gradients):
            raise ValueError('All gradients are zero')
        student.verify_frozen()
        results.append(dict(group=group, loss=float(loss.detach()), H_loss=float(lh.detach()),
            T_loss=float(lt.detach()) if lt is not None else None,
            parameters_with_gradient=len(gradients), full_tokens=int(outputs['interface'].shape[1]),
            frozen_parameters_verified=True))
        del outputs, loss, lh, lt, gradients
    write_json(Path(a.out), dict(status='PASS_SINGLE_DEVICE_H_T_HT_FORWARD_BACKWARD',
        environment=backend(), global_index=a.index, token=data['token'], results=results,
        trainable_parameters=student.module_manifest['trainable_parameters'],
        lora_modules=len(student.lora_modules), optimizer_steps=0,
        multi_GPU_training_verified=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--paths', required=True)
    p.add_argument('--workspace', required=True)
    p.add_argument('--index', type=int, default=3902)
    p.add_argument('--out', required=True)
    main(p.parse_args())
