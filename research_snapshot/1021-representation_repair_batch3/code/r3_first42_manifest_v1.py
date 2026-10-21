"""Freeze user-specified entries, executable semantics and provenance before testing."""
from r3_common import *


def main():
    destination=ROOT/'manifests/first42_v1.json'
    assert not destination.exists(), 'Never overwrite a frozen candidate pack'
    source=BATCH1/'vlm_repair_v1/oracle_policy_groups/20261017T172416/SUMMARY.json'
    pool=next(v for v in read(source)['compatible_pools'] if v['cases']==12146)
    entries=[dict(id='Base',kind='Base',root=None,arm=None,sources=[])]
    for item in pool['groups']['upstream_representation']['methods']:
        panel=BATCH1/'vlm_repair_v1/oracle_all/panels'/(item['panel']+'.json')
        arm=next(v['arm'] for v in read(panel)['methods'] if v.get('arm',{}).get('id')==item['id'])
        entries.append(dict(id=item['id'],kind='analytic',root=str(BATCH1),arm=arm,
                            sources=[dict(path=str(panel),sha256=sha(panel),source_entry=item['id'])]))
    assert len(entries)==12
    pack=BATCH2/'provenance/final_confirmation/PACK.json';parts={};sources={}
    for policy in read(pack)['policies'][1:]:
        path=BATCH2/policy['policy'];assert sha(path)==policy['policy_sha256'];data=read(path)
        items=data['configuration']['model']['parts'] if policy['kind']=='finite' else data['parts']
        for item in items:
            if item['id'] in parts:assert parts[item['id']]==item
            parts[item['id']]=item
            sources.setdefault(item['id'],[]).append(dict(path=str(path),sha256=sha(path),policy_id=policy['id'],slot=item['slot']))
    assert len(parts)==30
    for ident,part in parts.items():
        assert part['kind']=='analytic'
        entries.append(dict(id=ident,kind='analytic',root=str(BATCH2),arm=part['arm'],sources=sources[ident]))
    assert len(entries)==42 and len({v['id'] for v in entries})==42
    semantic_keys=['block','group','method','alpha','cap','gate','gate_threshold','control_kind','fit_sha256','observation_gate']
    aliases={};assets={}
    for entry in entries:
        arm=entry['arm']
        if arm:
            asset=Path(entry['root'])/arm['fit_path'];assert sha(asset)==arm['fit_sha256'];assets[str(asset)]=arm['fit_sha256']
            if arm.get('observation_gate'):
                gate=arm['observation_gate']['fit'];asset=Path(entry['root'])/gate['path'];assert sha(asset)==gate['sha256'];assets[str(asset)]=gate['sha256']
            semantic={k:arm[k] for k in semantic_keys if k in arm}
        else:semantic=dict(kind='Base')
        entry['execution_key']=digest(semantic);aliases.setdefault(entry['execution_key'],[]).append(entry['id'])
    result=dict(status='FROZEN_BEFORE_FORMAL_INFERENCE',time=stamp(),entries=entries,entry_count=42,
                executable_semantics=len(aliases),execution_aliases=aliases,assets=assets,
                sources=[dict(path=str(source),sha256=sha(source)),dict(path=str(pack),sha256=sha(pack))],
                checkpoint_sha256='23fb949b10387efeff87e093703d5faf41b61b9e5ead16d4076661e3c7c08a20',
                seeds=[0,1,2,3,4],seed_formula='int(sha256(f"{token}|20261008|{j}".encode()).hexdigest()[:8],16)',
                score_selection='strict unrounded real PDMS; no external failure gate; no extra safety filter',
                preserve_internal_observation_only_gates=True,
                endpoints=dict(R1='Best actual entry separately per seed, mean over five',
                               R2='One actual entry maximizing five-seed mean, same entry on all five',
                               R3='Choose entry on S0-S2 only; fixed entry evaluated on S3-S4, negative gains retained'),
                tie_break='Base first; then smaller actual relative edit; then stable candidate ID',
                teacher_snapshot='Freeze first42 once complete; later live-best updates do not freeze snapshots',
                test_use='Only diagnostic evaluation of frozen entries; never student supervision or candidate expansion')
    atomic(destination,result)
    print(json.dumps(dict(path=str(destination),sha256=sha(destination),entries=len(entries),executable_semantics=len(aliases))),flush=True)


if __name__=='__main__':main()
