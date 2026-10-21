from common import *
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic
import numpy as np

def main():
    base=ROOT/'runs/vlm_all_layers_20261016_v1';p=read(base/'PROTOCOL.json');tasks=read(base/'tasks.json');receipts=list((base/'receipts').glob('collect_*.json'));assert len(receipts)==len(tasks)==6456
    known={t['id']:t for t in tasks};seen=np.zeros(103288,dtype=bool);records=0
    for receipt in receipts:
        proof=read(receipt);path=base/'results'/receipt.name;assert sha(path)==proof['result_sha256'];r=read(path);assert r['task']==known[r['task']['id']]
        for row in r['records']:
            i=row['global_index'];assert not seen[i];seen[i]=True;records+=1
    assert seen.all() and records==103288
    assert not list((base/'failures').glob('*.json')) and not list(base.glob('node*/FAILED.json'))
    smoke=[read(base/f'node{n}/SMOKE_PASS.json') for n in [0,1]]
    stage=read(VOUT/'COLLECTION_STAGE_AUDIT.json');assert stage['status']=='PASS'
    atomic(VOUT/'COLLECTION_COMPLETE.json',dict(status='PASS',time=stamp(),chunks=len(receipts),cases=records,scene_indices_exact_once=True,nodes=2,cards=32,blocks=62,cells=2272,stage_audit_sha256=sha(VOUT/'COLLECTION_STAGE_AUDIT.json'),source_files_hash_validation='all NPZ hashes assigned across pivot nodes; formal source acceptance pending both pivot cache manifests',model_rerun=False,queues_retained=True))
    print('COLLECTION_LOGICAL_ACCEPT_PASS',records)
if __name__=='__main__':main()
