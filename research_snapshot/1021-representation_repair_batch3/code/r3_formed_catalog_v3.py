"""Metadata-only formed-candidate audit, separate from historical search grids.

Whole-exploration selected library parts and frozen complete policies remain
eligible for full evaluation. Unselected checkpoints/CV/grid points stay in the
raw inventory and may enter only the explicitly separate expansion workflow.
"""
from r3_common import *
from collections import Counter


def arm_key(arm):
    if arm.get('method')=='legacy':return arm_key(arm['legacy_arm'])
    if arm.get('method')=='trajectory_scale':return dict(method='trajectory_scale',factor=arm['factor'])
    if arm.get('method')=='combination':return dict(parts=[arm_key(v) for v in arm['parts']])
    # Preserve unknown fields rather than risk merging different operators.
    ignored={'id','parent','ungated_parent','fit_id','oracle_diagnostic'}
    # Keep fit paths so independently fitted assets retain their identity.
    return {k:v for k,v in arm.items() if k not in ignored}



def part_key(part):
    kind=part['kind']
    if kind=='analytic':return dict(kind=kind,arm=arm_key(part['arm']))
    if kind=='learned':
        task=part['training_task'];assert task['heldout_fold']==-1
        return dict(kind=kind,block=task['block'],group=task['group'],cap=task['cap'],strength=part.get('strength',1.),checkpoint_sha256=part['checkpoint']['sha256'],checkpoint_path=part['checkpoint']['path'],training_task=task['id'])
    if kind=='delta':
        fit=part['fit'];assert fit['heldout_fold']==-1
        return dict(kind=kind,block=fit['block'],group=fit['group'],cap=fit['cap'],strength=part.get('strength',1.),fit_sha256=fit['sha256'],fit_path=fit['path'],fit_id=fit['id'])
    raise ValueError(kind)


def main():
    destination=ROOT/'manifests/FORMED_CATALOG_DRAFT_V3.json';assert not destination.exists()
    items={};scanned=Counter();excluded=Counter();sources=[]
    def add(kind,definition,semantic,source,alias):
        ident='formed_'+digest(dict(kind=kind,semantic=semantic))[:24]
        if ident not in items:items[ident]=dict(id=ident,kind=kind,definition=definition,semantic=semantic,sources=[],aliases=[],scope='formed_whole_exploration_fit',asset_audit='PENDING',runtime_audit='PENDING',full_evaluation_required_without_unresolved_prescreen=True)
        item=items[ident]
        if alias not in item['aliases']:item['aliases'].append(alias)
        if source not in item['sources']:item['sources'].append(source)
    summary=BATCH1/'vlm_repair_v1/oracle_policy_groups/20261017T172416/SUMMARY.json'
    pool=next(p for p in read(summary)['compatible_pools'] if p['cases']==12146)
    for panel in pool['panels']:
        path=BATCH1/'vlm_repair_v1/oracle_all/panels'/(panel+'.json')
        for method in read(path)['methods']:
            arm=method['arm'];kind='batch1_upstream' if 'block' in arm else 'batch1_action_or_postprocess'
            add(kind,dict(root=str(BATCH1),arm=arm),arm_key(arm),dict(path=str(path),sha256=sha(path)),arm['id']);scanned['batch1_final_entries']+=1
    folders=['expert_library_selection','variant_library_selection','spatial_library_selection','unified_bc_library_selection','unified_bcs_library_selection','causal_library_selection']
    for name in folders:
        for path in sorted((BATCH2/'analysis'/name).glob('*.json')):
            data=read(path)
            if data.get('heldout_fold')!=-1:excluded['crossvalidation_library_files']+=1;continue
            source=dict(path=str(path),sha256=sha(path));scanned['whole_exploration_libraries']+=1
            for part in data.get('arms',[]):add('batch2_'+part['kind'],part,part_key(part),source,part['id'])
    latest=read(BATCH2/'analysis/all_data_policy_catalog/LATEST.json');catalog=BATCH2/latest['path'];assert sha(catalog)==latest['sha256'];cache={}
    policy_entries=list(read(catalog)['entries'])
    # Explicitly selected finite policies are complete configurations; raw
    # finite training checkpoints in the broad catalog are archived separately.
    for entry in read(BATCH2/'provenance/final_confirmation/PACK.json')['policies'][1:]:
        policy_entries.append(dict(kind=entry['kind'],artifact=entry['policy'],sha256=entry['policy_sha256'],policy=entry['id']))
    for path in sorted((BATCH2/'token_policies').glob('*/POLICY.json')):
        data=read(path)
        if data.get('heldout_fold')!=-1:excluded['crossvalidation_token_policies']+=1;continue
        policy_entries.append(dict(kind='token',artifact=str(path.relative_to(BATCH2)),sha256=sha(path),policy=path.parent.name))
    for entry in policy_entries:
        if 'artifact' not in entry:excluded['unselected_finite_checkpoints_pending_expansion_audit']+=1;continue
        path=BATCH2/entry['artifact']
        if str(path) not in cache:
            assert sha(path)==entry['sha256'];cache[str(path)]=read(path)
        data=cache[str(path)];assert data['heldout_fold']==-1
        source=dict(path=str(path),sha256=entry['sha256']);kind=entry['kind'];scanned['whole_exploration_complete_policy_entries']+=1
        parts=data['configuration']['model']['parts'] if kind in ['joint','finite'] else data['parts']
        for part in parts:add('batch2_'+part['kind'],part,part_key(part),source,part['id'])
        ordered=[dict(definition=part_key(p),slot=p.get('slot')) for p in parts]
        if kind in ['hard','candidate']:
            semantic=dict(model_sha256=data['model_sha256'],tier=data['tier'],feature_sha256=data['feature_meta']['sha256'],risk_penalty=data['risk_penalty'],threshold=data['threshold'],parts=ordered)
        elif kind in ['joint','finite']:
            setting=data['configuration'];model=setting['model']
            semantic=dict(checkpoint_sha256=setting['checkpoint']['sha256'],tier=model['tier'],model_kind=model.get('kind','finite_fixed_strength_argmax'),input_dimension=model['input_dimension'],
                          multiplier=setting.get('multiplier',1.),identity_threshold=setting.get('identity_threshold',1.01),force_Base=setting.get('force_Base',False),parts=ordered)
        elif kind=='token':
            c=data['critic'];semantic=dict(checkpoint_sha256=c['checkpoint']['sha256'],context_view=c.get('context_view','post_valid'),risk_penalty=c['risk_penalty'],threshold=c['threshold'],parts=ordered)
        else:raise ValueError(kind)
        add('batch2_policy_'+kind,dict(policy_path=entry['artifact'],policy_sha256=entry['sha256']),semantic,source,entry.get('system','')+'/'+entry['policy'])
    sources.append(dict(path=str(catalog),sha256=latest['sha256']))
    result=dict(status='DRAFT_FORMED_METADATA_LINEAGE_PRESERVED_NOT_EXECUTION_ADMISSION',time=stamp(),entries=sorted(items.values(),key=lambda v:(v['kind'],v['id'])),
                counts=dict(Counter(v['kind'] for v in items.values())),scanned=dict(scanned),excluded_from_formed=dict(excluded),sources=sources,
                selection='Identity and fit scope only; no test or online outcome screening',first42_still_has_priority=True,
                expansion_workflow='Historical grids and new configurations require unresolved training/development prescreen; formed candidates keep full evaluation scope')
    atomic(destination,result);atomic(ROOT/'provenance/FORMED_CATALOG_DRAFT_V3_SUMMARY.json',{k:v for k,v in result.items() if k!='entries'})
    print(json.dumps({k:v for k,v in result.items() if k not in ['entries','sources']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
