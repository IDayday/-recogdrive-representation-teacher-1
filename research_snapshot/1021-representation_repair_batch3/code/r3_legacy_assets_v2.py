"""Resolve legacy head-fit names exactly as the frozen original editors do."""
from r3_common import *
from collections import Counter


def main():
    catalog=read(ROOT/'manifests/FORMED_CATALOG_DRAFT_V3.json');assets={};entries=[]
    def register(path,role):
        path=Path(path).resolve();assert path.is_relative_to(BATCH1)
        if str(path) not in assets:
            value=sha(path);sidecar=path.with_suffix('.json');metadata=read(sidecar) if sidecar.exists() else {}
            declared=metadata.get('fit_sha256',metadata.get('sha256'))
            if declared:assert value==declared
            assets[str(path)]=dict(sha256=value,role=role,declared_hash_checked=bool(declared),bytes=path.stat().st_size)
        return str(path)
    def paths(arm):
        found=[]
        if arm['method']=='legacy':return paths(arm['legacy_arm'])
        if arm['method']=='trajectory_scale':return found
        if 'fit' in arm:
            for item in arm.get('components',[arm]):
                for name in [item['fit']]+([item['alternative_basis']] if item.get('alternative_basis') else []):
                    found.append(register(BATCH1/'candidate_repair_v1/fits'/(name+'.npz'),'candidate_action_fit'))
                if item.get('benefit_path'):found.append(register(BATCH1/item['benefit_path'],'candidate_action_gate'))
        else:
            for layer in arm.get('multi_layers',[arm['layer']]):
                for step in arm.get('multi_steps',arm['steps']):
                    found.append(register(BATCH1/'repair_v1/fits'/f's{step}_l{layer}_k{arm["k"]}.npz','legacy_action_fit'))
                    overlay=BATCH1/'repair_v1/fits'/f'natural_learn_l{layer}_k{arm["k"]}.npz'
                    if step==4 and overlay.exists():found.append(register(overlay,'legacy_action_overlay'))
            if arm.get('benefit_path'):found.append(register(BATCH1/arm['benefit_path'],'legacy_action_gate'))
        return sorted(set(found))
    for entry in catalog['entries']:
        if entry['kind']!='batch1_action_or_postprocess':continue
        try:needed=paths(entry['definition']['arm']);entries.append(dict(id=entry['id'],status='PASS_EXACT_DERIVED_ASSET_FINGERPRINTS',paths=needed))
        except Exception as error:entries.append(dict(id=entry['id'],status='FAILED_ASSET_RESOLUTION',error=repr(error)))
    destination=ROOT/'manifests/LEGACY_ASSET_AUDIT_V2.json';assert not destination.exists()
    result=dict(status='COMPLETE_REQUIRES_RUNTIME_ADMISSION',time=stamp(),assets=assets,entries=entries,counts=dict(Counter(v['status'] for v in entries)),
                source_editor_sha256={str(BATCH1/'code'/name):sha(BATCH1/'code'/name) for name in ['repair_engine.py','candidate_repair_engine.py','candidate_repair_queue.py']},no_test_or_online_outcomes_used=True)
    atomic(destination,result);print(json.dumps(dict(status=result['status'],assets=len(assets),counts=result['counts'])),flush=True)


if __name__=='__main__':main()
