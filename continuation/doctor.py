"""Check assets and hardware before loading the portable student."""
import argparse
import json
import importlib.metadata
from pathlib import Path
from continuation.layout import BATCHES,REPO,Runtime,sha,write_json

def check(a):
    runtime=Runtime(a.paths,a.workspace);root=runtime.workspace/BATCHES[3]
    scientific=runtime.read(runtime.workspace/BATCHES[0]/'configs/repair_final_baseline.json')
    checks={}
    version=importlib.metadata.version('transformers')
    checks['transformers']=version
    checks['frozen_reference_transformers']='4.37.0; other versions require actual pilot and gradient validation'
    for name in ['checkpoint','vlm','maps','navtrain_logs','navtrain_sensor']+([]if a.models_only else ['navtrain_metric']):
        path=Path(runtime.paths[name]).expanduser()
        if not path.exists():raise FileNotFoundError(f'{name}: {path}')
        checks[name]=str(path)
    if not a.skip_weight_hashes:
        if sha(runtime.paths['checkpoint'])!=scientific['checkpoint_sha256']:raise ValueError('RL checkpoint SHA differs from the frozen official RL Base')
        core=['model.safetensors','config.json','configuration_intern_vit.py','configuration_internvl_chat.py',
              'modeling_intern_vit.py','modeling_internvl_chat.py','conversation.py','generation_config.json',
              'added_tokens.json','tokenizer_config.json','special_tokens_map.json','vocab.json']
        for name in core:
            if sha(Path(runtime.paths['vlm'])/name)!=scientific['vlm_sha256'][name]:raise ValueError('VLM/tokenizer fingerprint differs: '+name)
        checks['model_fingerprints']='PASS'
    else:checks['model_fingerprints']='NOT_CHECKED'
    index=json.loads((REPO/'research_snapshot/INDEX.json').read_text())
    for item in index['files']:
        if item['role'].startswith('historical_'):continue
        if sha(runtime.workspace/item['workspace_path'])!=item['sha256']:raise ValueError('Frozen source/manifest differs: '+item['workspace_path'])
    checks['frozen_sources_and_definitions']='PASS'
    if a.models_only:
        result=dict(status='PASS_PORTABLE_MODEL_CHECK',checks=checks,weights_fully_verified=not a.skip_weight_hashes,paths_sha256=sha(a.paths))
        write_json(runtime.workspace/'PORTABLE_MODEL_CHECK.json',result);return result
    scenes=runtime.read(root/'manifests/R2_TRAINING_SCENES_V2.json')
    if len(scenes)!=103288:raise ValueError('Unexpected scene population')
    train=runtime.read(root/'manifests/TRAIN_INDICES_V2.json');valid=runtime.read(root/'manifests/DEVELOPMENT_512_V1.json')
    if len(train)!=85339 or len(valid)!=512:raise ValueError('Frozen exposure sets differ')
    if set(train)&set(valid) or not all(scenes[i]['subset']=='exploration' and scenes[i]['pool']in ['I','P']for i in train):
        raise ValueError('Train/development isolation failed')
    for row in {row['raw_path']:row for row in scenes}.values():
        if not Path(row['raw_path']).is_file():raise FileNotFoundError(row['raw_path'])
    for index in valid:
        if not Path(scenes[index]['metric_cache']).is_file():raise FileNotFoundError('Rebuild development metrics: '+scenes[index]['metric_cache'])
    if a.targets:
        required=set(train)|set(valid)
        for index in required:
            folder=root/'runs/full_context_replay_v1/cases'/scenes[index]['token']
            if not (folder/'RESULT.json').is_file()or not(folder/'full_context.npz').is_file():raise FileNotFoundError('Missing exact teacher target: '+str(folder))
        checks['training_targets']=dict(cases=len(required),status='PRESENT; teacher acceptance and dataset loader verify SHA256')
    if a.hardware:
        import torch
        if torch.cuda.device_count()!=a.devices:raise ValueError('Visible GPU count differs from the intended topology')
        names=[torch.cuda.get_device_name(i)for i in range(a.devices)]
        if any('A800'not in name for name in names):raise ValueError('Expected NVIDIA A800 target; record a new migration for other hardware')
        checks['hardware']=dict(devices=names,torch=torch.__version__,cuda=torch.version.cuda)
    result=dict(status='PASS_PORTABLE_ASSET_CHECK',checks=checks,weights_fully_verified=not a.skip_weight_hashes)
    write_json(runtime.workspace/'PORTABLE_ASSET_CHECK.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--skip-weight-hashes',action='store_true');p.add_argument('--targets',action='store_true')
    p.add_argument('--hardware',action='store_true');p.add_argument('--devices',type=int,default=8)
    p.add_argument('--models-only',action='store_true')
    print(json.dumps(check(p.parse_args()),ensure_ascii=False,indent=2))
