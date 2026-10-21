"""Development evaluation without the source machine's 42-way score tensors."""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import os
from pathlib import Path
from continuation.layout import BATCHES,Runtime,sha,write_json
from continuation.runtime_workers import initialize_score

def evaluate(student,indices,rank,world_size,output_stage,loader_workers=2):
    import numpy as np
    import torch
    import torch.distributed as dist
    from d4_prefetch_v1 import PrefetchLoader
    from d4_dataset_v2 import TeacherDataset
    from repair_score import score_group
    from r3_incremental_audit_v1 import FIELDS
    runtime=Runtime(os.environ['RECOGDRIVE_CONTINUATION_PATHS'],os.environ['RECOGDRIVE_CONTINUATION_WORKSPACE'])
    root=runtime.workspace/BATCHES[3];manifest=student.config['scene_manifest'];local=indices[rank::world_size]
    from continuation.identity import backend
    protocol=root/'runs/full_context_replay_v1/PORTABLE_PROTOCOL.json'
    same_teacher_environment=protocol.exists()and runtime.read(protocol).get('environment')==backend()
    dataset=TeacherDataset(local,manifest,student.config['scene_manifest_sha256'])
    if not all(dataset.scenes[i]['subset']=='validation'for i in indices):raise ValueError('Development contains training scenes')
    loader=PrefetchLoader(dataset,workers=loader_workers,prefetch_factor=2,timeout=120)
    records=[];student.eval();base_engine=None
    with ProcessPoolExecutor(max_workers=1,mp_context=mp.get_context('spawn'),initializer=initialize_score)as pool:
        with torch.no_grad():
            for data in loader:
                hidden={}
                handle=student.agent.action_head.feature_encoder.register_forward_pre_hook(lambda module,args:hidden.update(value=args[0]))
                try:out=student(data['features'],data['token'],0,trajectory=False)
                finally:handle.remove()
                if not torch.equal(out['input_ids'][0],data['target']['input_ids'].cuda()):raise ValueError('Input IDs differ')
                if not torch.equal(out['attention_mask'][0],data['target']['attention_mask'].cuda()):raise ValueError('Attention mask differs')
                h=out['interface'];squared=(h[0]-data['target']['teacher_interface'].cuda()).square();den=data['teacher_residual_squared_sum']
                mse=float(squared.mean());relative=float((squared.sum()/den).sqrt())if den>0 else None
                trajectories=torch.stack([student.sample(data['features'],hidden['value'],h,data['token'],j)[0]for j in range(5)]).float().cpu().numpy()
                row=dataset.scenes[data['global_index']]
                submitted=[dict(arm='student',seed_index=j,trajectory=v.tolist())for j,v in enumerate(trajectories)]
                base_quality=data['target_backend_Base_quality']if same_teacher_environment else None
                if base_quality is None:
                    # Optional old-snapshot migration still needs an actual CUDA Base comparison.
                    from vlm_intervene_v4 import Engine
                    from r3_runtime import prediction
                    if base_engine is None:base_engine=Engine()
                    base_hidden=base_engine.forward_native(data['features'])
                    submitted.extend(dict(arm='Base',seed_index=j,trajectory=prediction(base_engine,data['features'],base_hidden,j,data['token'])[0].float().cpu().numpy().tolist())for j in range(5))
                scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=sha(row['metric_cache']),
                    scoring=student.scientific['scoring'],records=submitted)).result(timeout=3600)
                q=np.asarray([[v['score'][f]for f in FIELDS]for v in scored if v['arm']=='student'])
                if base_quality is None:base_quality=[[v['score'][f]for f in FIELDS]for v in scored if v['arm']=='Base']
                records.append(dict(global_index=data['global_index'],token=row['token'],session=row['session'],pool=row['pool'],
                    quality=q.tolist(),Base_quality=base_quality,trajectories=trajectories.tolist(),interface_MSE=mse,relative_interface_error=relative))
    folder=root/output_stage;path=folder/f'rank{rank:02d}.json'
    write_json(path,dict(status='PASS_DEVELOPMENT_NATIVE_INFERENCE_AND_FRESH_SCORE',rank=rank,cases=records,indices=local,
        GT_used=False,Base_backend='same target CUDA backend',source_42way_tensors_required=False))
    dist.barrier();summary=None
    if rank==0:
        combined=[]
        for other in range(world_size):combined.extend(runtime.read(folder/f'rank{other:02d}.json')['cases'])
        if sorted(v['global_index']for v in combined)!=sorted(indices):raise ValueError('Development coverage differs')
        q=np.asarray([v['quality']for v in combined]);b=np.asarray([v['Base_quality']for v in combined]);safety={}
        for name in ['no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound']:
            col=FIELDS.index(name);safety[name]=dict(new=int(((q[:,:,col]<1)&(b[:,:,col]>=1)).sum()),removed=int(((q[:,:,col]>=1)&(b[:,:,col]<1)).sum()))
        summary=dict(status='PASS_DEVELOPMENT_PANEL',cases=len(combined),outputs=5*len(combined),noises=list(range(5)),
            PDMS=float(q[:,:,0].mean()*100),Base_PDMS=float(b[:,:,0].mean()*100),gain=float((q[:,:,0]-b[:,:,0]).mean()*100),
            mean_interface_MSE=float(np.mean([v['interface_MSE']for v in combined])),safety=safety,GT_used=False,
            source_rank_files=[dict(path=str((folder/f'rank{r:02d}.json').relative_to(root)),sha256=sha(folder/f'rank{r:02d}.json'))for r in range(world_size)],
            checkpoint_selection_metric='PDMS only; no extra safety eligibility',Base_backend='same target CUDA backend')
        write_json(folder/'SUMMARY.json',summary)
    box=[summary];dist.broadcast_object_list(box,src=0);student.verify_frozen();return box[0]
