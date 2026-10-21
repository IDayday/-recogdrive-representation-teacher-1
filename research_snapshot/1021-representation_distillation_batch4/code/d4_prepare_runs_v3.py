"""Freeze first matched H/T/HT run configs; engineer exact training program first."""
from d4_common_v2 import *
import argparse


def main(a):
    import numpy as np
    source=ROOT/'manifests/R2_TRAINING_SCENES_V2.json';scenes=read(source)
    train=ROOT/'manifests/TRAIN_INDICES_V2.json';validation=read(ROOT/'manifests/VALIDATION_INDICES_V1.json')
    rng=np.random.default_rng(2026102105);panel=sorted(rng.choice(validation,size=512,replace=False).tolist())
    panel_path=ROOT/'manifests/DEVELOPMENT_512_V1.json'
    if panel_path.exists():assert read(panel_path)==panel
    else:atomic(panel_path,panel)
    if a.engineering:
        pools=[([s['global_index'] for s in scenes if s['subset']=='exploration' and s['pool']=='I' and s['Base_any_below70']],8),
               ([s['global_index'] for s in scenes if s['subset']=='exploration' and s['pool']=='I' and not s['Base_any_below70']],24),
               ([s['global_index'] for s in scenes if s['subset']=='exploration' and s['pool']=='P'],32)]
        rng=np.random.default_rng(2026102106);indices=sorted(np.concatenate([rng.choice(p,size=n,replace=False) for p,n in pools]).tolist())
        train=ROOT/'manifests/ENGINEERING_TRAIN_64_V1.json';assert not train.exists() or read(train)==indices
        if not train.exists():atomic(train,indices)
        panel_path=ROOT/'manifests/ENGINEERING_DEVELOPMENT_16_V1.json';assert not panel_path.exists() or read(panel_path)==panel[:16]
        if not panel_path.exists():atomic(panel_path,panel[:16])
    calibration=read(ROOT/'configs/LOSS_CALIBRATION_V1.json');assert calibration['status']=='FROZEN_TRAIN_ONLY_INTERFACE_GRADIENT_SCALE'
    assert 61156 not in calibration['configuration']['indices']
    code_names=['d4_common.py','d4_common_v2.py','d4_student_v1.py','d4_distributed_v1.py','d4_dataset_v2.py','d4_development_eval_v2.py','d4_train_v3.py']
    hashes={n:sha(ROOT/'code'/n) for n in code_names};registered=[]
    for assigned in read(ROOT/'resources/ALLOCATION_V1.json')['nodes']:
        node=next(n for n in read(B3/'resources/REGISTRY.json')['nodes'] if n['name']==assigned['node']);world=len(node['devices'])
        group=assigned['group'];run=('training_engineering_v3_' if a.engineering else 'distillation_main_v3_')+group
        config=dict(run_id=run,group=group,node=node['name'],job=node['job'],devices=node['devices'],world_size=world,training_entrypoint='d4_train_v3.py',
            scene_manifest=str(source),scene_manifest_sha256=sha(source),train_indices=str(train),train_indices_sha256=sha(train),
            development_indices=str(panel_path),development_indices_sha256=sha(panel_path),teacher_frozen_sha256=sha(B3/'teachers/first42_v1/FROZEN.json'),
            code_hashes=hashes,initialization_seed=2026102101,data_seed=2026102102,loader_seed=2026102104,lora_rank=16,lora_alpha=32,lora_dropout=0.,
            gradient_checkpointing=True,lora_learning_rate=5e-5,projection_learning_rate=1e-4,optimizer='AdamW',weight_decay=0.,adam_betas=[.9,.999],adam_epsilon=1e-8,
            global_batch_size=64,microbatch_size=1,epochs=2 if a.engineering else 5,warmup_steps=2 if a.engineering else 200,minimum_lr_ratio=.1,
            lambda_H=0. if group=='T' else 1.,lambda_T=0. if group=='H' else 1. if group=='T' else calibration['lambda_T'],
            trajectory_loss=dict(position='SmoothL1 mean',xy_scales_metres=[40.,10.],heading='0.1*mean(1-cos(delta_heading))'),
            interface_loss='Full-token full-coordinate MSE; one per scene exposure',gradient_clip_norm=1.,
            loader_workers=2,prefetch_factor=2,log_every_steps=1 if a.engineering else 25,checkpoint_every_steps=250,
            early_evaluation_step=1 if a.engineering else 50,noise_rule='(epoch + seed(token,0)%5)%5; native whole stochastic DDIM stream isolated by fork_rng',
            independent_evaluation_noises=[5,6,7,8,9],GT_used=False,training_subset='exploration_I_and_P_only',
            dataset_sampling='Natural scene frequency with common epoch shuffle; round tail to global batch',
            checkpoint_primary='Final epoch, matched scene/noise exposure across H/T/HT',checkpoint_secondary='Best PDMS on identical five epoch-end development panels; report exposure differences',
            early_panel_diagnostic_only=True,engineering_only=a.engineering,formal_weights_reinitialized_from_RL_Base=True)
        path=ROOT/'configs'/('training_engineering_v3' if a.engineering else 'distillation_main_v3')/(group+'.json')
        assert not path.exists();atomic(path,config);registered.append(dict(group=group,path=str(path.relative_to(ROOT)),sha256=sha(path),run_id=run,node=node['name']))
    proof=ROOT/'provenance'/('TRAINING_ENGINEERING_CONFIGS_V3.json' if a.engineering else 'MAIN_CONFIGS_V3.json')
    atomic(proof,dict(status='FROZEN_ENGINEERING_CONFIGS' if a.engineering else 'FROZEN_MATCHED_MAIN_CONFIGS',time=stamp(),runs=registered,code_hashes=hashes,
        engineering_only=a.engineering,GT_used=False,formal_runs_not_started=True))
    print(json.dumps(dict(status='CONFIGURATIONS_FROZEN',engineering=a.engineering,runs=registered)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engineering',action='store_true');main(p.parse_args())
