"""Prepare untouched official navtest after frozen development selection; no old scores read."""
from common import *
import csv
from concurrent.futures import ThreadPoolExecutor
from repair_final_queue import stage
from representation_prepare import session

def main():
    setup('repair/final_prepare')
    root=ROOT/'repair_v1';lock=root/'TEST_LOCK.json';assert read(lock)['status']=='LOCKED_BEFORE_TEST_ACCESS'
    run='repair_final_test_20261016_v1';base=ROOT/'runs'/run;assert not base.exists()
    source=ROOT.parent/'1010-il_baseline';legacy=read(source/'config/execution_protocol.json');cfg=read(ROOT/'configs/baseline.json')
    assert legacy['vlm_sha256']==cfg['vlm_sha256'];sourceproof={}
    for rel in ['code/worker.py','vendor/model/recogdrive_features.py','vendor/model/utils/internvl_preprocess.py','config/input_features.json']:
        assert sha(source/rel)==legacy['frozen_files'][rel];sourceproof[rel]=sha(source/rel)
    assert sha(ROOT/'code/upstream/model/recogdrive_features.py')==sourceproof['vendor/model/recogdrive_features.py']
    rows=sorted([r for r in csv.DictReader((source/'manifests/cases.csv').open()) if r['cohort']=='navtest'],key=lambda r:r['token'])
    assert len(rows)==12146 and len({r['token'] for r in rows})==len(rows)
    inputs={r['token']:r for r in csv.DictReader((source/'manifests/input_features.csv').open()) if r['cohort']=='navtest'}
    assert set(inputs)=={r['token'] for r in rows}
    train=read(ROOT/'manifests/natural_s0.json');assert not {r['token'] for r in train}&{r['token'] for r in rows}
    assert not {r['session'] for r in train}&{session(r['log_name']) for r in rows}
    generation_sha=sha(source/'config/execution_protocol.json')
    def check(item):
        index,row=item;folder=Path(row['feature_dir']);ident=read(folder/'complete.json');expected=inputs[row['token']]
        assert Path(expected['feature_dir']).resolve()==folder.resolve()
        assert ident['token']==row['token'] and ident['vlm_sha256']==cfg['vlm_sha256'] and ident['vlm_dtype']=='torch.bfloat16'
        assert ident['execution_protocol_sha256']==generation_sha
        assert sha(folder/'complete.json')==expected['generation_protocol_sha256']
        assert sha(folder/'internvl_feature.gz')==expected['feature_sha256']
        assert sha(folder/'trajectory_target.gz')==expected['target_sha256']
        return dict(row,global_index=index,session=session(row['log_name']),subset='independent_test',quality='unscored',
            feature_sha256=expected['feature_sha256'],target_sha256=expected['target_sha256'],cache_identity_sha256=expected['generation_protocol_sha256'],metric_sha256=sha(row['metric_cache']))
    panel=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=16) as pool:
        for i,row in enumerate(pool.map(check,enumerate(rows)),1):
            panel.append(row)
            if i%512==0:print(json.dumps(dict(status='TEST_INPUT_CHECK',cases=i,total=len(rows),seconds=time.monotonic()-began)),flush=True)
    count=stage(base,'final_test',panel,read(root/'final_test_arms.json'),[0,1,2,3,4],chunk=16)
    final_cfg=dict(cfg,cohort='navtest',samples=len(rows),source_logs=len({r['log_name'] for r in rows}),no_navtest_access=False,
        seed_indices=[0,1,2,3,4],seed_formula='int(sha256(f"{token}|20261008|{j}").hexdigest()[:8],16)',
        test_selection_lock_sha256=sha(lock),test_cache_execution_protocol_sha256=generation_sha,
        parent_baseline_config_sha256=sha(ROOT/'configs/baseline.json'),manifest_sha256=sha(base/'stages/final_test/panel.json'),
        manifest_format='JSON frozen final test panel',feature_cache_policy='Read-only 1010 VLM cache, original schema verified by dedicated adapter; all RL trajectories/scores freshly computed')
    final_cfg.pop('identity');final_cfg['identity']=digest(final_cfg);assert not (ROOT/'configs/repair_final_baseline.json').exists();atomic(ROOT/'configs/repair_final_baseline.json',final_cfg)
    atomic(root/'FINAL_TEST_INPUTS_READY.json',dict(status='PASS',time=stamp(),run=run,tasks=count,cases=len(panel),
        lock_sha256=sha(lock),test_cache_execution_protocol_sha256=generation_sha,legacy_source_sha256=sourceproof,
        all_input_feature_target_identity_metric_hashes_verified=True,train_test_tokens_and_sessions_disjoint=True,
        reused_old_model_trajectories_or_scores=False,model_config_sha256=sha(ROOT/'configs/repair_final_baseline.json')))
    print(json.dumps(dict(status='FINAL_TEST_INPUTS_READY',cases=len(panel),tasks=count)),flush=True)

if __name__=='__main__':main()
