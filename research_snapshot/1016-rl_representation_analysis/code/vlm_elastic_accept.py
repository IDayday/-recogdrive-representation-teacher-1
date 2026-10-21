"""Dynamic participating-rank acceptance with unchanged scientific checks."""
from common import *
import numpy as np
from vlm_elastic_registry import DEST,BASE,allowed_ranks
from repair_queue_v2 import atomic_unique as atomic

def audit_participating_ranks(stage):
    protocol=read(BASE/'stages'/stage/'PROTOCOL.json')
    receipts=sorted((BASE/'receipts').glob(stage+'_a*.json'))
    assert len(receipts)==protocol['tasks'],'Only a complete stage can receive final acceptance.'
    latest={};allowed=allowed_ranks();registry=read(DEST/'REGISTRY.json')
    for p in receipts:
        r=read(p);assert r['rank'] in allowed,('Unregistered GPU rank',r['rank']);latest[r['rank']]=p
    assert latest
    arms={a['id']:a for a in read(BASE/'stages'/stage/'arms.json')};checks=[];node_checks=[]
    for node in registry['nodes']:
        actual=set(node['gpu_ranks'])&set(latest)
        if not actual:continue
        if node['kind']=='legacy':
            proof=read(ROOT/node['smoke_proof']);assert proof['status']=='PASS' and proof['cards']==node['cards']
        else:
            assert sha(ROOT/node['config'])==node['config_sha256']
            config=read(ROOT/node['config']);folder=ROOT/config['folder'];proof=read(folder/'GPU_SMOKE_PASS.json')
            assert proof['status']=='PASS' and set(proof['ranks'])==set(node['gpu_ranks'])
            assert read(folder/'PREFLIGHT.json')['status']=='PASS' and read(folder/'GPU_ENABLED.json')['status']=='ENABLED'
            assert read(folder/'ENGINEERING_PASS.json')['all_record_fields_exact']
            for item in proof['proofs']:assert sha(ROOT/item['path'])==item['sha256']
        node_checks.append(dict(node=node['id'],configured_ranks=node['gpu_ranks'],actual_stage_ranks=sorted(actual),all_configured_cards_smoke_pass=True))
    for rank,p in sorted(latest.items()):
        proof=read(p);path=BASE/'results'/p.name;assert sha(path)==proof['result_sha256'];doc=read(path)
        assert doc['rank']==rank and doc['task']['stage']==stage
        for v in doc['records']:
            assert v['seed']==seed(v['token'],v['seed_index']) and v['quality']==quality(v['score']['score'])
            assert np.asarray(v['trajectory']).shape==(8,3) and np.isfinite(v['trajectory']).all()
            assert all(np.isfinite(x) and 0<=x<=1+1e-8 for x in v['score'].values())
            assert v['edit']['relative_edit_max']<=arms.get(v['arm'],{}).get('cap',0)+1e-6
        checks.append(dict(rank=rank,path=str(path.relative_to(ROOT)),sha256=proof['result_sha256'],records=len(doc['records'])))
    folder=DEST/'acceptance'/stage/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    atomic(folder/'RANK_ACCEPTANCE.json',dict(status='PASS',time=stamp(),stage=stage,participating_ranks=sorted(latest),
        participating_card_identities=len(latest),nodes=node_checks,checks=checks,receipts=len(receipts),
        no_fixed_world_size_assertion=True,all_actual_participants_audited=True,
        all_configured_devices_individually_smoke_verified=True,registry_snapshot=registry,
        note='A phase can straddle rolling node changes. Historical card identities are not simultaneous active cards.',
        original_seed_trajectory_score_quality_cap_checks_unchanged=True))
    return checks
