"""Validate real CPU tensor IPC, then start this node's independent smoke."""
from d4_common_v2 import *
import argparse
from types import SimpleNamespace


def main(a):
    from d4_ipc_smoke_v1 import main as ipc
    from d4_launch_train_v3 import main as launch
    assigned=next(n for n in read(ROOT/'resources/ALLOCATION_V1.json')['nodes'] if n['node']==a.node)
    marker=ROOT/'provenance'/('IPC_SHORT_TMPDIR_'+a.node+'.json')
    if not marker.exists():ipc(SimpleNamespace(node=a.node))
    else:assert read(marker)['common_source_sha256']==sha(ROOT/'code/d4_common_v2.py')
    launch(SimpleNamespace(config=str(ROOT/'configs/training_engineering_v3'/(assigned['group']+'.json')),resume=None,stop_after_epoch=1))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
