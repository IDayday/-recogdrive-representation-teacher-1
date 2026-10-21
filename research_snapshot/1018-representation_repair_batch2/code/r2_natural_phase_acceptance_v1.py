"""Actual output/coverage audit for a frozen natural run, without tuning it."""
from r2_common import *
import argparse
from collections import defaultdict


def main(args):
    setup('natural_phase_acceptance',threads=2)
    import numpy as np
    stage=(ROOT/args.stage).resolve();assert stage.is_relative_to(ROOT/'runs')
    specification=read(stage/'SPECIFICATION.json');pack=read(ROOT/specification['pack'])
    assert sha(ROOT/specification['pack'])==specification['pack_sha256']
    rows=read(ROOT/specification['rows']);assert sha(ROOT/specification['rows'])==specification['rows_sha256']
    entries={p['id']:p for p in pack['policies']};parts={};own={}
    for entry in pack['policies']:
        if entry['kind']=='Base':continue
        policy=read(ROOT/entry['policy']);assert sha(ROOT/entry['policy'])==entry['policy_sha256'] and policy['heldout_fold']==-1
        selected=policy['configuration']['model']['parts'] if entry['kind'] in ['joint','finite'] else policy['parts']
        own[entry['id']]=selected
        for part in selected:parts[part['id']]=part
    expected_arms={'baseline',*entries}
    if pack.get('include_raw_experts',True):expected_arms.update('candidate_'+p for p in parts)
    expected_arms.update('base_resample_'+str(i+1) for i in range(pack.get('base_resampling_extra_candidates',0)))
    receipts=[read(p) for p in (stage/'receipts').glob('*.json')]
    by_worker=defaultdict(list)
    for receipt in receipts:by_worker[receipt['worker']].append(receipt)
    selected=[];roots=[];accepted_nodes=[];excluded_nodes=[]
    cloud_path=ROOT/'resources/CLOUD_LATEST.json';cloud=read(cloud_path)
    running={n['name'] for n in cloud['nodes'] if n['status']=='Running'}
    for node in read(ROOT/'resources/NODES.json')['nodes']:
        if node['name'] not in running or not node.get('active_for_batch2',True) or not node['devices']:
            excluded_nodes.append(node['name']);continue
        assert (RUN/'nodes'/node['name']/'GPU_SMOKE_PASS.json').exists()
        accepted_nodes.append(node)
        live=read(RUN/'nodes'/node['name']/'LIVE.json');children=live['children']
        for key,state in children.items():
            if not key.startswith('gpu_1_'):continue
            device=int(key.rsplit('_',1)[1])
            if device not in node['devices']:continue
            assert state['returncode'] is None
            worker=node['job']+'-master-0_'+str(state['pid'])
            assert by_worker[worker],('No actual completed output from configured main GPU worker',node['name'],device)
            receipt=max(by_worker[worker],key=lambda r:r['time'])
            selected.append(receipt);roots.append(dict(node=node['name'],job=node['job'],device=device,worker=worker,task=receipt['task']['id']))
    assert len(roots)==sum(len(n['devices']) for n in accepted_nodes)
    checked=0;choices=0;sources=[];tokens=set()
    for receipt in selected:
        result=receipt['result'];assert receipt['status']=='COMPLETE' and sha(ROOT/result['path'])==result['sha256']
        output=read(ROOT/result['path']);assert output['mode']==specification['mode']
        assert output['actual_fresh_generation_and_independent_scoring'] and output['base_weights_frozen']
        task=receipt['task'];indices=specification['panel'][task['start']:task['end']]
        expected={(rows[i]['token'],arm,noise) for i in indices for arm in expected_arms for noise in specification['seeds']}
        lookup={(r['token'],r['arm'],r['seed_index']):r for r in output['records']}
        assert len(lookup)==len(output['records']) and set(lookup)==expected
        for record in output['records']:
            assert record['subset']==specification['mode'] and np.shape(record['trajectory'])==(8,3)
            assert np.isfinite(record['trajectory']).all() and all(np.isfinite(v) for v in record['score'].values())
            assert record['seed']==seed(record['token'],record.get('noise_draw_index',record['seed_index']))
            if record['arm'].startswith('base_resample_'):assert record['noise_draw_index']>=5
            entry=entries.get(record['arm'])
            if entry and entry['kind'] in ['Base','candidate','finite']:
                choice=record['choice'];p=own.get(entry['id'],[]);assert 0<=choice<=len(p)
                arm='baseline' if choice==0 else 'candidate_'+p[choice-1]['id']
                reference=lookup[(record['token'],arm,record['seed_index'])]
                assert record['trajectory']==reference['trajectory'] and record['score']==reference['score'];choices+=1
            checked+=1;tokens.add(record['token'])
        sources.append(dict(path=result['path'],sha256=result['sha256'],worker=receipt['worker']))
    target=stage/'AGENT_FIRST_PHASE_ACCEPTANCE.json';assert not target.exists()
    proof=dict(status='PASS_ACTUAL_OUTPUT_EVERY_CONFIGURED_MAIN_GPU_WORKER',time=stamp(),
        mode=specification['mode'],stage=args.stage,physical_devices=len(roots),roots=roots,
        complete_chunks_in_snapshot=len(receipts),sampled_chunks=len(selected),sampled_cases=len(tokens),
        actual_records_checked=checked,actual_whole_candidate_choices_checked=choices,sources=sources,
        pack_sha256=specification['pack_sha256'],cloud_snapshot_time=cloud['time'],
        registered_but_not_active_running_nodes_excluded=excluded_nodes,
        only_protocol_and_engineering_checked=True,
        no_selection_or_parameters_changed=True)
    atomic(target,proof)
    print(json.dumps({k:proof[k] for k in ['status','mode','physical_devices','complete_chunks_in_snapshot','sampled_chunks','sampled_cases','actual_records_checked','actual_whole_candidate_choices_checked']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
