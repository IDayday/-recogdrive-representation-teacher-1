"""Verify full target coverage before admitting a newly generated CUDA teacher."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from continuation.layout import BATCHES,sha,write_json

def main(a):
    root=Path(a.workspace).resolve()/BATCHES[3];stage=root/'runs/full_context_replay_v1'
    scenes=json.loads((root/'manifests/R2_TRAINING_SCENES_V2.json').read_text())
    protocol=json.loads((stage/'PORTABLE_PROTOCOL.json').read_text())
    protocol_sha=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    def check(row):
        folder=stage/'cases'/row['token'];record=json.loads((folder/'RESULT.json').read_text())
        if record['global_index']!=row['global_index']or record['candidate']!=row['teacher_candidate']or record['GT_used']:
            raise ValueError('Teacher identity failure')
        if record.get('portable_protocol_sha256')!=protocol_sha:raise ValueError('Mixed teacher versions')
        path=root/record['arrays']['path']
        if not path.is_file():raise FileNotFoundError(path)
        if a.hash_arrays and sha(path)!=record['arrays']['sha256']:raise ValueError('Target SHA mismatch')
        return record['source_H_byte_exact'],record['source_trajectory_byte_exact'],record['source_trajectory_max_abs_error']
    with ThreadPoolExecutor(max_workers=a.workers)as pool:results=list(pool.map(check,scenes))
    proof=dict(status='PASS_COMPLETE_PORTABLE_FIXED_R2_TEACHER',cases=len(results),full_padding_context=True,GT_used=False,
        reference_mode=protocol['reference_mode'],source_H_exact_cases=sum(x[0]for x in results),
        source_trajectory_exact_cases=sum(x[1]for x in results),max_source_trajectory_error=max(x[2]for x in results),
        all_arrays_rehashed=a.hash_arrays,source_exposure_labels_frozen=True)
    write_json(stage/'AGENT_ACCEPTANCE.json',proof);print(json.dumps(proof,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--hash-arrays',action='store_true')
    p.add_argument('--workers',type=int,default=8);main(p.parse_args())
