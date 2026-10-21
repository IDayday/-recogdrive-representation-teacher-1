"""Read every device's semantic receipts before admitting that node."""
from r3_common import *
import argparse


def accept(name):
    config=read(ROOT/'resources/REGISTRY.json');node=next(n for n in config['nodes'] if n['name']==name)
    expected=read(ROOT/'configs/engineering_v1.json');rows=read(expected['rows']);tokens=[rows[i]['token'] for i in expected['indices']]
    sources=[]
    for device in node['devices']:
        p=ROOT/'runs/resident_engineering_v1'/name/('device%02d'%device)/'PASS.json';d=read(p)
        assert d['status']=='PASS_RESIDENT_PHYSICAL_DEVICE' and d['node']==name and d['job']==node['job'] and d['device']==device
        assert d['config_sha256']==sha(ROOT/'configs/engineering_v1.json') and d['runtime_sha256']==sha(ROOT/'code/r3_runtime.py')
        assert [v['token'] for v in d['checks']]==tokens
        assert all(v['records']==24 and v['native_hidden_cache_exact'] and v['all_trajectories_scores_and_interfaces_equal_single_device'] for v in d['checks'])
        for token in tokens:
            data=read(p.parent/(token+'.json'))
            assert data['status']=='PASS' and len(data['records'])==24
            assert sha(ROOT/data['interface_file'])==data['interface_sha256']
            assert all(v['same_execution_interface'] and v['seed']==seed(token,v['seed_index']) for v in data['records'])
        sources.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),worker_pid=d['worker_pid']))
    assert len({v['worker_pid'] for v in sources})==len(node['devices'])
    result=dict(status='PASS_ACTUAL_CONFIGURED_DEVICES',time=stamp(),node=name,job=node['job'],devices=node['devices'],
                checks_per_device=len(tokens),records_per_device=48,real_trajectory_score_and_same_execution_interface=True,sources=sources)
    atomic(ROOT/'resources/nodes'/name/'THIRD_BATCH_GPU_ACCEPTED.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);accept(p.parse_args().node)
