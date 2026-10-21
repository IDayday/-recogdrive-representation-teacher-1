"""Accept every newly added lane from actual first42 replay records."""
from r3_common import *
import argparse


def main(a):
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node)
    assert read(ROOT/'resources/nodes'/a.node/'THIRD_BATCH_GPU_ACCEPTED.json')['status']=='PASS_ACTUAL_CONFIGURED_DEVICES'
    manifest=ROOT/a.manifest;group=read(manifest);selected=[w for w in group['workers'] if w['node']==a.node]
    assert {(w['device'],w['lane']) for w in selected}=={(d,l) for d in node['devices'] for l in [1,2,3]}
    proofs=[];pids=set();expected_tokens=None;frozen_pack=sha(ROOT/'manifests/first42_v1.json')
    for worker in selected:
        folder=ROOT/'runs/extra_engineering_v1'/worker['worker'];proof=read(folder/'PASS.json');meta=proof['worker']
        assert proof['status']=='PASS_ALL42_FIVE_NOISE_GOLDEN_EXACT' and proof['freeze_unchanged']
        for key in ['node','device','lane','worker']:assert meta[key]==worker[key]
        assert meta['job']==node['job'] and meta['hostname'].startswith(node['job']+'-') and meta['pid'] not in pids;pids.add(meta['pid'])
        result_path=ROOT/proof['result']['path'];assert sha(result_path)==proof['result']['sha256'];result=read(result_path)
        task=result['task'];assert task['indices']==[60,1] and task['pack_sha256']==frozen_pack and task['seeds']==[0,1,2,3,4]
        for case in result['cases']:
            path=ROOT/case['path'];assert sha(path)==case['sha256'];actual=read(path)
            golden=read(ROOT/'runs/first42_engineering_v2/cases'/actual['token']/'RESULT.json')
            assert actual['records']==golden['records'] and actual['selection']==golden['selection'] and len(actual['records'])==210
            assert sha(ROOT/actual['interfaces']['path'])==actual['interfaces']['sha256']
        proofs.append(dict(path=str((folder/'PASS.json').relative_to(ROOT)),sha256=sha(folder/'PASS.json'),pid=meta['pid']))
    target=ROOT/a.output;assert not target.exists()
    proof=dict(status='PASS_NEW_NODE_FOUR_LANES_ACTUAL_GOLDEN',time=stamp(),node=a.node,job=node['job'],devices=node['devices'],
        models_per_device=4,extra_model_processes=len(proofs),extra_golden_output_records=len(proofs)*2*210,
        native_lane_admission_sha256=sha(ROOT/'resources/nodes'/a.node/'THIRD_BATCH_GPU_ACCEPTED.json'),
        manifest_sha256=sha(manifest),source_sha256=sha(ROOT/'code/r3_extra_worker_v2.py'),proofs=proofs,
        original_batch3_only=True,existing_three_distillation_assignments_unchanged=True,no_nodes_released=True)
    atomic(target,proof);print(json.dumps({k:v for k,v in proof.items() if k!='proofs'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--manifest',required=True);p.add_argument('--output',required=True);main(p.parse_args())
