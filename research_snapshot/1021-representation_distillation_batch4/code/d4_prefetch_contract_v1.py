"""Check exact ordered real feature/target loading without socket transport."""
from d4_common_v2 import *
import argparse
import socket


def main(a):
    setup('prefetch_contract/'+a.node,threads=1)
    import torch
    from d4_dataset_v2 import TeacherDataset
    from d4_prefetch_v1 import PrefetchLoader
    torch.set_num_threads(1)
    node=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    manifest=ROOT/'manifests/R2_TRAINING_SCENES_V2.json';indices=[3902,6,3902,6]
    dataset=TeacherDataset(indices,str(manifest),sha(manifest))
    reference={i:dataset[i] for i in range(2)};count=0
    for position,item in enumerate(PrefetchLoader(dataset,workers=2,prefetch_factor=2,timeout=60)):
        old=reference[position%2];assert item['token']==old['token'] and item['global_index']==old['global_index']
        for kind in ['features','target']:
            assert set(item[kind])==set(old[kind])
            for key in old[kind]:assert torch.equal(item[kind][key],old[kind][key]),(kind,key)
        count+=1
    assert count==4
    proof=dict(status='PASS_REAL_ORDERED_THREAD_PREFETCH_EXACT',time=stamp(),node=a.node,real_cases=2,ordered_fetches=count,
        workers=2,depth=4,all_features_and_full_teacher_targets_exact=True,tensor_IPC_used=False,GT_used=False,
        prefetch_source_sha256=sha(ROOT/'code/d4_prefetch_v1.py'),dataset_source_sha256=sha(ROOT/'code/d4_dataset_v2.py'))
    atomic(ROOT/'provenance'/('PREFETCH_CONTRACT_'+a.node+'.json'),proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
