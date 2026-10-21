"""Exercise actual Torch tensor IPC with private TMPDIR; no model or GPU load."""
from d4_common_v2 import *
import argparse
import socket


class SmallDataset:
    def __len__(self):return 8
    def __getitem__(self,index):
        import torch
        return dict(index=index,features=torch.full((2,3,8,8),float(index)),target=torch.arange(128,dtype=torch.float32))


def worker_init(index):setup('ipc_smoke_deep_path_worker/'+str(os.getpid()),threads=1)


def main(a):
    setup('ipc_smoke_deep_path_parent/'+a.node,threads=1)
    import torch
    from torch.utils.data import DataLoader
    node=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    loader=DataLoader(SmallDataset(),batch_size=None,num_workers=2,multiprocessing_context='spawn',worker_init_fn=worker_init,timeout=30)
    seen=[]
    for item in loader:
        index=item['index'];assert torch.equal(item['features'],torch.full((2,3,8,8),float(index)))
        assert torch.equal(item['target'],torch.arange(128,dtype=torch.float32));seen.append(index)
    assert seen==list(range(8))
    proof=dict(status='PASS_TORCH_TENSOR_IPC_SHORT_TASK_TMPDIR',time=stamp(),node=a.node,hostname=socket.gethostname(),workers=2,
        cases=len(seen),TMPDIR=os.environ['TMPDIR'],maximum_expected_socket_path_bytes=len((os.environ['TMPDIR']+'/pymp-00000000/listener-00000000').encode()),
        task_private_only=True,global_environment_unchanged=True,common_source_sha256=sha(ROOT/'code/d4_common_v2.py'))
    atomic(ROOT/'provenance'/('IPC_SHORT_TMPDIR_'+a.node+'.json'),proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
