"""Independent matched-noise student/Base scoring on the target backend.

Training never receives these scores. A test checkpoint is locked before any
test sample is read; source and target-backend results retain distinct identities.
"""
import argparse
import json
from pathlib import Path
import os
from continuation.layout import BATCHES,Runtime,sha,write_json

def main(a):
    runtime=Runtime(a.paths,a.workspace).bootstrap();root=runtime.workspace/BATCHES[3]
    config=runtime.read(a.config);config_sha=sha(a.config)
    from continuation.identity import backend,verified_models
    verified_models(runtime)
    if not 0<=a.rank<a.world_size:raise ValueError('Invalid evaluation shard')
    if a.development and a.cohort!='navtrain':raise ValueError('Development is a navtrain-only panel')
    if a.limit is not None and a.limit<=0:raise ValueError('Limit must be positive')
    if a.cohort=='navtest' and not a.allow_navtest:raise ValueError('Final test requires --allow-navtest after configuration/checkpoint selection')
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    identity=dict(checkpoint_sha256=sha(a.checkpoint),configuration_sha256=config_sha,
        cohort=a.cohort,noises=a.noises,subset=a.subset,development=a.development,limit=a.limit,
        student_uses_teacher_or_true_scores=False,backend='target CUDA',environment=backend())
    lock=out/'FROZEN_MODEL.json'
    if lock.exists() and json.loads(lock.read_text())!=identity:raise ValueError('Use a new evaluation directory')
    write_json(lock,identity)
    import numpy as np
    import torch
    from d4_student_v1 import Student
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from r3_runtime import prediction
    from repair_score import score_group
    state=torch.load(a.checkpoint,map_location='cpu',weights_only=False)
    if state['configuration_sha256']!=config_sha:raise ValueError('Checkpoint/configuration differ')
    student=Student(config)
    with torch.no_grad():
        for name,p in student.named_parameters():
            if p.requires_grad:p.copy_(state['trainable'][name])
    del state;student.eval();student.verify_frozen();engine=Engine()
    path=root/'manifests/R2_TRAINING_SCENES_V2.json' if a.cohort=='navtrain' else runtime.workspace/BATCHES[1]/'manifests/frozen_evaluation_test_rows_v1.json'
    rows=runtime.read(path)
    indices=runtime.read(root/'manifests/DEVELOPMENT_512_V1.json')if a.development else [i for i,row in enumerate(rows)if a.subset=='all'or row.get('subset')==a.subset]
    if a.limit:indices=indices[:a.limit]
    indices=indices[a.rank::a.world_size];noises=[int(v)for v in a.noises.split(',')]
    if len(noises)!=len(set(noises))or not set(noises)<=set(range(10)):raise ValueError('Use distinct S0-S9 indices')
    gains=[]
    for index in indices:
        row=rows[index];dest=out/'cases'/(row['token']+'.json')
        if dest.exists():
            old=json.loads(dest.read_text())
            if old['identity']!=identity:raise ValueError('Existing case belongs to another evaluation')
            gains.append(old['mean_gain']);continue
        features=raw_features(row);records=[]
        with torch.no_grad():
            hidden=engine.forward_native(features)
            for noise in noises:
                base,_=prediction(engine,features,hidden,noise,row['token'])
                result=student(features,row['token'],noise,trajectory=True)
                for kind,value in [('Base',base),('student',result['prediction'][0])]:
                    records.append(dict(kind=kind,seed_index=noise,trajectory=value.float().cpu().numpy().tolist()))
        records=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=sha(row['metric_cache']),scoring=engine.cfg['scoring'],records=records))
        base=np.asarray([v['score']['score']for v in records if v['kind']=='Base'])
        actual=np.asarray([v['score']['score']for v in records if v['kind']=='student'])
        gain=float((actual-base).mean()*100);gains.append(gain)
        write_json(dest,dict(identity=identity,global_index=index,token=row['token'],session=row['session'],
            subset=row.get('subset',a.cohort),pool=row.get('pool','not_defined_on_test'),
            records=records,mean_gain=gain,GT_used=False))
        student.verify_frozen();engine.verify_engine()
        if len(gains)%50==0:print(json.dumps(dict(rank=a.rank,completed=len(gains),total=len(indices))),flush=True)
    write_json(out/f'COMPLETE_rank{a.rank:03d}.json',dict(status='COMPLETE_TARGET_BACKEND_EVALUATION_SHARD',identity=identity,
        rank=a.rank,world_size=a.world_size,cases=len(indices),mean_gain=float(np.mean(gains))if gains else None,
        source_PPU_scores_not_substituted_for_target_Base=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--config',required=True);p.add_argument('--checkpoint',required=True);p.add_argument('--out',required=True)
    p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain');p.add_argument('--noises',default='0,1,2,3,4')
    p.add_argument('--development',action='store_true');p.add_argument('--allow-navtest',action='store_true')
    p.add_argument('--subset',choices=['all','exploration','validation'],default='all')
    p.add_argument('--rank',type=int,default=0);p.add_argument('--world-size',type=int,default=1);p.add_argument('--limit',type=int)
    main(p.parse_args())
