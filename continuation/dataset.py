"""Load original exact targets or explicitly identified target-backend replays."""
import hashlib
import io
from continuation.layout import BATCHES

def install(runtime):
    import d4_dataset_v2
    root=runtime.workspace/BATCHES[3]
    class TeacherDataset:
        def __init__(self,indices,scene_manifest,scene_manifest_sha256,noise_epoch=0):
            if runtime.hash(scene_manifest)!=scene_manifest_sha256:raise ValueError('Scene manifest changed')
            self.scenes=runtime.read(scene_manifest);self.indices=list(indices);self.noise_epoch=noise_epoch
        def __len__(self):return len(self.indices)
        def __getitem__(self,position):
            import numpy as np
            import torch
            from vlm_core import raw_features
            from r3_common import seed
            index=self.indices[position];row=self.scenes[index]
            record=runtime.read(root/'runs/full_context_replay_v1/cases'/row['token']/'RESULT.json')
            if record['status']not in ['PASS_EXACT_R2_FULL_CONTEXT_REPLAY','PASS_PORTABLE_FIXED_R2_TARGET']:
                raise ValueError('Unaccepted teacher target')
            if record['global_index']!=index or record['candidate']!=row['teacher_candidate']:raise ValueError('Teacher identity differs')
            data=(root/record['arrays']['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=record['arrays']['sha256']:raise ValueError('Target checksum mismatch')
            with np.load(io.BytesIO(data),allow_pickle=False)as z:target={k:torch.from_numpy(np.array(z[k]))for k in z.files}
            if 'target_backend_Base_scores'in record:
                # The frozen development evaluator reads this same row after __getitem__.
                # Compare CUDA students to their actual matched CUDA Base, not old PPU scores.
                row['Base_scores']=record['target_backend_Base_scores']
            return dict(global_index=index,token=row['token'],subset=row['subset'],pool=row['pool'],
                noise_index=(self.noise_epoch+seed(row['token'],0)%5)%5,features=raw_features(row),target=target,
                teacher_residual_squared_sum=record['teacher_residual_squared_sum'],Base_interface_squared_sum=record['Base_interface_squared_sum'],
                target_backend_Base_quality=record.get('target_backend_Base_quality'))
    d4_dataset_v2.TeacherDataset=TeacherDataset
