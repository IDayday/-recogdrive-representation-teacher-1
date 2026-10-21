"""Run an existing frozen expansion pack on ordinary GPUs, with real PDMS scoring."""
import argparse
import hashlib
import json
from pathlib import Path
from continuation.layout import BATCHES,Runtime,sha,write_json

def main(a):
    runtime=Runtime(a.paths,a.workspace).bootstrap()
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from r3_formed_scene_v2 import Scene
    from r3_select_generic_v1 import select
    from repair_score import score_group
    pack=runtime.read(a.pack);entries=[dict(id='Base',kind='Base',definition={})]+pack['entries']
    if len({v['id']for v in entries})!=len(entries):raise ValueError('Duplicate candidate IDs')
    row_path=runtime.workspace/BATCHES[0]/'manifests/natural_s0.json'if a.cohort=='navtrain'else runtime.workspace/BATCHES[1]/'manifests/frozen_evaluation_test_rows_v1.json'
    rows=runtime.read(row_path);out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    identity=dict(pack_sha256=sha(a.pack),cohort=a.cohort,seeds=list(range(5)),source_index_sha256=sha(runtime.workspace/'PORTABLE_WORKSPACE.json'))
    if a.cohort=='navtest'and not a.allow_navtest:raise ValueError('Frozen test diagnostic needs --allow-navtest; never feed test outcomes into expansion')
    if (out/'PROTOCOL.json').exists()and json.loads((out/'PROTOCOL.json').read_text())!=identity:raise ValueError('Use a new output directory')
    write_json(out/'PROTOCOL.json',identity);engine=Engine();indices=list(range(len(rows)))
    if a.limit:indices=indices[:a.limit]
    for index in indices[a.rank::a.world_size]:
        row=rows[index];folder=out/'cases'/row['token'];dest=folder/'RESULT.json'
        if dest.exists():
            if json.loads(dest.read_text())['identity']!=identity:raise ValueError('Case identity mismatch')
            continue
        features=raw_features(row);records=[];interfaces={}
        with torch.no_grad():
            scene=Scene(engine,features,row['token']);valid=engine.inputs['attention_mask'][0].bool()
            for entry in entries:
                for noise in range(5):
                    branch=scene.evaluate(entry,noise);h=branch.interface[0,valid].float().cpu().numpy()
                    hashed=hashlib.sha256(h.tobytes()).hexdigest();interfaces[hashed]=h
                    records.append(dict(arm=entry['id'],seed_index=noise,relative_edit=branch.relative_edit,
                        trajectory=branch.trajectory.float().cpu().numpy().tolist(),interface_sha256=hashed))
        records=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=sha(row['metric_cache']),scoring=engine.cfg['scoring'],records=records))
        choice=select(records,[v['id']for v in entries]);winning={v['arm']for kind in ['R1','R2','R3']for v in choice[kind]}
        keep={v['interface_sha256']for v in records if v['arm']in winning};folder.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(folder/'winner_interfaces.npz',**{key:interfaces[key]for key in keep},
            input_ids=engine.inputs['input_ids'][0].cpu().numpy(),valid_token_positions=np.flatnonzero(valid.cpu().numpy()))
        write_json(dest,dict(status='COMPLETE_PORTABLE_FROZEN_PACK',identity=identity,global_index=index,token=row['token'],
            session=row['session'],records=records,selection=choice,GT_used=False,
            interface_scope='ordered valid tokens; not the full padding context used for student H loss'))
        engine.verify_engine()
    write_json(out/f'COMPLETE_rank{a.rank:03d}.json',dict(identity=identity,rank=a.rank,world_size=a.world_size))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--pack',required=True);p.add_argument('--out',required=True);p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain')
    p.add_argument('--allow-navtest',action='store_true');p.add_argument('--rank',type=int,default=0);p.add_argument('--world-size',type=int,default=1)
    p.add_argument('--limit',type=int);main(p.parse_args())
