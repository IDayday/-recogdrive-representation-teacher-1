"""Environment identity for regenerated teacher targets and student comparison."""
import importlib.metadata
import json
from pathlib import Path
from continuation.layout import sha

def backend():
    import torch
    versions={}
    for package in ['transformers','tokenizers','diffusers','numpy','scipy','torchvision','timm',
                    'flash-attn','nuplan-devkit','shapely']:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]='MISSING'
    return dict(torch=torch.__version__,cuda=torch.version.cuda,device=torch.cuda.get_device_name(0),packages=versions)

def verified_models(runtime):
    path=runtime.workspace/'PORTABLE_MODEL_CHECK.json'
    proof=json.loads(path.read_text())
    if proof.get('status')!='PASS_PORTABLE_MODEL_CHECK'or not proof.get('weights_fully_verified')or proof.get('paths_sha256')!=sha(runtime.paths_file):
        raise ValueError('Run doctor --models-only with full weight hashes for these local paths')
    return proof
