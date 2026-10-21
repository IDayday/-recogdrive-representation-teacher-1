"""Fresh H/T/HT from the official RL Base with matched 8-GPU exposure/budget."""
import argparse
import json
from pathlib import Path
from continuation.layout import BATCHES,sha,write_json

def main(a):
    root=Path(a.workspace).resolve()/BATCHES[3]
    for group in ['H','T','HT']:
        source=root/'configs/distillation_main_v4'/(group+'.json');config=json.loads(source.read_text())
        config.update(run_id=a.prefix+'_'+group,world_size=a.world_size,devices=list(range(a.world_size)),node='portable',job=None,
            portable_fresh=True,source_configuration_sha256=sha(source),target_backend='NVIDIA A800',
            teacher_version='fixed R2 choices replayed on target; frozen source scene exposure labels')
        if config['global_batch_size']%a.world_size:raise ValueError('World size must divide global batch 64')
        path=root/'configs/portable'/(config['run_id']+'.json')
        if path.exists()and json.loads(path.read_text())!=config:raise ValueError('Use a new run prefix')
        write_json(path,config);print(path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--world-size',type=int,default=8)
    p.add_argument('--prefix',default='distillation_a800_fresh');main(p.parse_args())
