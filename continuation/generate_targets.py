"""Replay only the already frozen R2 winner; no search, re-selection, or GT.

Every full-padding H and five trajectories come from the same actual branch.
Exact mode compares both H bytes and trajectories with the PPU reference.
Record mode creates an explicitly new target-backend teacher version.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import time
from continuation.layout import BATCHES,REPO,Runtime,sha,write_json

class Reference:
    def __init__(self):
        self.index=json.loads((REPO/'reference/continuation_20261022/r2/INDEX.json').read_text())
        item=self.index['interface_metadata'];path=REPO/item['path']
        if sha(path)!=item['sha256']:raise ValueError('Reference integrity failure')
        with gzip.open(path,'rt')as stream:self.interfaces=json.load(stream)
    @lru_cache(maxsize=2)
    def block(self,number):
        import numpy as np
        item=self.index['trajectory_blocks'][number];path=REPO/item['path']
        if sha(path)!=item['sha256']:raise ValueError('Reference trajectory integrity failure')
        with np.load(path,allow_pickle=False)as z:return np.array(z['trajectories'])
    def get(self,index):return self.interfaces[index],self.block(index//4096)[index%4096]

def main(a):
    runtime=Runtime(a.paths,a.workspace).bootstrap();root=runtime.workspace/BATCHES[3]
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from r3_runtime import prediction
    from r3_first42_rollout_v2 import FitBank,observation_gate
    from r3_incremental_audit_v1 import FIELDS
    from repair_score import score_group
    from d4_common import save_arrays
    from continuation.identity import backend,verified_models
    verified_models(runtime)
    reference=Reference();manifest=root/'manifests/R2_TRAINING_SCENES_V2.json'
    if sha(manifest)!=reference.index['source_scene_manifest_sha256']:raise ValueError('Frozen R2 scene identities changed')
    scenes=runtime.read(manifest);pack_path=runtime.workspace/BATCHES[2]/'teachers/first42_v1/PACK.json'
    pack=runtime.read(pack_path);entries={e['id']:e for e in pack['entries']}
    stage=root/'runs/full_context_replay_v1';protocol=dict(schema=1,scene_manifest_sha256=sha(manifest),
        pack_sha256=sha(pack_path),reference_mode=a.reference_mode,fixed_R2_choice=True,GT_used=False,
        full_padding_context=True,source_I_P_E_exposure_labels_frozen=True,
        environment=backend(),note='record mode is a target-backend teacher version; not a bitwise PPU continuation')
    if (stage/'PORTABLE_PROTOCOL.json').exists()and json.loads((stage/'PORTABLE_PROTOCOL.json').read_text())!=protocol:
        raise ValueError('Use a new workspace for a different teacher protocol')
    write_json(stage/'PORTABLE_PROTOCOL.json',protocol)
    indices=list(range(len(scenes)))
    if a.indices:indices=runtime.read(a.indices)
    if a.limit:indices=indices[:a.limit]
    if not 0<=a.rank<a.world_size:raise ValueError('Invalid shard')
    indices=indices[a.rank::a.world_size];engine=Engine();bank=FitBank();began=time.monotonic();completed=0
    for index in indices:
        row=scenes[index];folder=stage/'cases'/row['token'];dest=folder/'RESULT.json'
        if dest.exists():
            old=json.loads(dest.read_text())
            if old.get('portable_protocol_sha256')!=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest():
                raise ValueError('Existing target has another identity; do not overwrite it')
            if sha(root/old['arrays']['path'])!=old['arrays']['sha256']:raise ValueError('Existing target is corrupt')
            completed+=1;continue
        entry=entries[row['teacher_candidate']];expected,expected_trajectories=reference.get(index)
        if entry['id']!=expected['candidate']:raise ValueError('Frozen winner changed')
        features=raw_features(row)
        with torch.no_grad():
            hidden=engine.forward_native(features);base_h=engine.prefix['interface_post']
            base_trajectories=[prediction(engine,features,hidden,j,row['token'])[0]for j in range(5)]
            condition,post=hidden,None;arm=entry['arm']
            if arm is not None:
                actual=arm
                if arm['gate']=='external_observation_qda_hard':
                    active,_=observation_gate(engine,entry['root'],arm);actual=dict(arm,gate='none')if active else None
                if actual is not None:
                    changed,_=engine.edited(actual,bank.get(entry['root'],actual));condition,post=engine.suffix(actual['block'],changed)
            trajectories=[];interface=None
            for j in range(5):
                trajectory,h=prediction(engine,features,condition,j,row['token'],post)
                if interface is not None and not torch.equal(h,interface):raise ValueError('Fixed branch H depends on action noise')
                interface=h;trajectories.append(trajectory)
            full=interface[0].float().cpu().numpy();values=torch.stack(trajectories).float().cpu().numpy()
            base_values=torch.stack(base_trajectories).float().cpu().numpy()
            ids=engine.inputs['input_ids'][0].cpu().numpy();attention=engine.inputs['attention_mask'][0].cpu().numpy()
            positions=engine.inputs['position_ids'][0].cpu().numpy()
            if full.shape!=(len(ids),384)or len(ids)<2800:raise ValueError('Incomplete padding context')
            h_sha=hashlib.sha256(full.tobytes()).hexdigest();h_exact=h_sha==expected['teacher_interface_sha256']
            t_exact=np.array_equal(values,expected_trajectories)
            error=float(np.max(np.abs(values-expected_trajectories)))
            write_json(stage/'reference_diagnostics'/f'{row["token"]}.json',dict(
                global_index=index,token=row['token'],source_H_byte_exact=h_exact,
                source_trajectory_byte_exact=t_exact,source_trajectory_max_abs_error=error,
                source_H_sha256=expected['teacher_interface_sha256'],target_H_sha256=h_sha))
            if a.reference_mode=='exact'and not(h_exact and t_exact):
                raise ValueError(f'Cross-backend reference differs: {row["token"]}, H exact={h_exact}, trajectory max error={error}; retain the diagnostic and choose a new workspace for record mode')
            residual=float((interface-base_h).square().sum().cpu());base_square=float(base_h.square().sum().cpu())
        scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=sha(row['metric_cache']),scoring=engine.cfg['scoring'],
            records=[dict(kind=kind,seed_index=j,trajectory=v.tolist())for kind,seq in [('Base',base_values),('teacher',values)]for j,v in enumerate(seq)]))
        quality=np.asarray([[v['score'][f]for f in FIELDS]for v in scored if v['kind']=='teacher'])
        base_scores=[v['score']['score']for v in scored if v['kind']=='Base']
        base_quality=[[v['score'][f]for f in FIELDS]for v in scored if v['kind']=='Base']
        folder.mkdir(parents=True,exist_ok=True);arrays=folder/'full_context.npz'
        values_to_save=dict(teacher_interface=full,teacher_trajectories=values,teacher_quality=quality,
            input_ids=ids,attention_mask=attention,position_ids=positions,valid_token_positions=np.flatnonzero(attention))
        if arrays.exists():
            with np.load(arrays,allow_pickle=False)as existing:
                if set(existing.files)!=set(values_to_save)or not all(np.array_equal(existing[k],v)for k,v in values_to_save.items()):
                    raise ValueError('An orphan target differs; preserve it and use a new workspace')
            hashed=sha(arrays)
        else:hashed=save_arrays(arrays,values_to_save)
        write_json(dest,dict(status='PASS_PORTABLE_FIXED_R2_TARGET',global_index=index,token=row['token'],session=row['session'],
            subset=row['subset'],pool=row['pool'],candidate=entry['id'],arrays=dict(path=str(arrays.relative_to(root)),sha256=hashed),
            full_tokens=len(ids),padding_tokens=int((attention==0).sum()),teacher_interface_sha256=h_sha,
            teacher_residual_squared_sum=residual,Base_interface_squared_sum=base_square,
            source_H_byte_exact=h_exact,source_trajectory_byte_exact=t_exact,source_trajectory_max_abs_error=error,
            target_backend_Base_scores=base_scores,target_backend_teacher_scores=quality[:,0].tolist(),
            target_backend_Base_quality=base_quality,
            source_teacher_scores=row['teacher_scores'],source_exposure_pool_frozen=row['pool'],
            portable_protocol_sha256=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest(),
            same_execution_interface=True,teacher_fixed_not_reselected=True,GT_used=False))
        completed+=1;engine.verify_engine()
        if completed%10==0:
            progress=dict(status='GENERATING_FIXED_R2_TARGETS',rank=a.rank,completed=completed,total=len(indices),
                elapsed_seconds=time.monotonic()-began,last_source_trajectory_error=error)
            write_json(stage/f'PORTABLE_PROGRESS_rank{a.rank:03d}.json',progress);print(json.dumps(progress),flush=True)
    write_json(stage/f'PORTABLE_COMPLETE_rank{a.rank:03d}.json',dict(status='COMPLETE_FIXED_R2_SHARD',rank=a.rank,world_size=a.world_size,
        cases=len(indices),protocol=protocol,elapsed_seconds=time.monotonic()-began))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--reference-mode',choices=['exact','record'],default='exact');p.add_argument('--rank',type=int,default=0)
    p.add_argument('--world-size',type=int,default=1);p.add_argument('--limit',type=int);p.add_argument('--indices')
    main(p.parse_args())
