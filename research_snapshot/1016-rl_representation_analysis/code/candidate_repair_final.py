"""Lock this round's test inputs/contrasts, smoke actual test inputs, append final queue stage."""
from common import *
import numpy as np
from candidate_repair_fit import OUT
from candidate_repair_followup import legacy,probe
from candidate_repair_queue import stage,Dispatch

RUN='candidate_repair_20261016_v1'

def main():
    setup('candidate_repair/final_setup');compatibility()
    assert read(OUT/'DEVELOPMENT_READY.json')['status']=='PASS'
    lock=read(OUT/'BEHAVIOR_SELECTION_LOCK.json');controls=read(OUT/'MATCHED_CONTROLS.json')['arms']+read(OUT/'MATCHED_CONTROL_SUPPLEMENT.json')['arms']
    selected_ids={a['id'] for a in lock['arms']};controls=[a for a in controls if a['parent'] in selected_ids]
    selected=list(lock['arms']);arms=list({a['id']:a for a in selected+legacy()+controls}.values())
    # All final controls accompany their already-frozen parents; no control-driven reselection.
    roles={k:v['summary']['arm']['id'] for k,v in lock['choices'].items()}
    manifest=ROOT/'runs/repair_final_test_20261016_v1/stages/final_test/panel.json';panel=read(manifest)
    assert len(panel)==12146 and all(r['cohort']=='navtest' for r in panel)
    train=read(ROOT/'manifests/natural_s0.json');assert not {r['token'] for r in train}&{r['token'] for r in panel}
    assert not {r['session'] for r in train}&{r['session'] for r in panel}
    contrasts=[]
    for a in selected:
        contrasts.append(dict(name=a['id']+'_vs_base',positive=[a['id']],reference=['baseline'],family='primary_base'))
        for role in ['safety_priority','pdms_priority']:
            contrasts.append(dict(name=a['id']+'_vs_legacy_'+role,positive=[a['id']],reference=['legacy_'+role],family='secondary_legacy'))
    for selected_parent in selected:
        parent=selected_parent['id'];role=parent;haar=[a['id'] for a in controls if a.get('parent')==parent and str(a.get('control_kind','')).startswith('haar')]
        assert len(haar)==3
        contrasts.append(dict(name=role+'_vs_matched_haar_mean',positive=[parent],reference=haar,family='secondary_matched_random'))
    fits={str(p.relative_to(ROOT)):sha(p) for p in (OUT/'fits').glob('*') if p.suffix in ['.npz','.json']}
    gates={str(p.relative_to(ROOT)):sha(p) for p in (OUT/'gates').glob('*') if p.suffix in ['.npz','.json']}
    freeze=dict(status='FROZEN_BEFORE_THIS_ROUND_TEST_COMPUTE',time=stamp(),arms=arms,roles=roles,contrasts=contrasts,
        selection_sha256=sha(OUT/'BEHAVIOR_SELECTION_LOCK.json'),controls_sha256=sha(OUT/'MATCHED_CONTROLS.json'),supplement_sha256=sha(OUT/'MATCHED_CONTROL_SUPPLEMENT.json'),
        input_manifest=str(manifest.relative_to(ROOT)),input_sha256=sha(manifest),fit_sha256=fits,gate_sha256=gates,
        bootstrap=2000,sign_flips=20000,inference_seed=20261016,unit='seeds averaged per scene, acquisition session cluster',
        multiplicity='Holm one-sided within each prespecified contrast family; all contrasts reported',
        test_seeds=[0,1,2,3,4],test_was_used_in_previous_round=True,results_used_to_change_this_selection=False)
    path=OUT/'FINAL_TEST_LOCK.json';assert not path.exists();atomic(path,freeze)
    atomic(OUT/'planned_stages/final_test_arms.json',arms)
    probe('final_test_train_anchors',arms)
    # Exercise new repairs on two real test-cache entries after lock, never before selection.
    import torch
    from worker import load_model
    from repair_test_features import load_features
    from repair_engine import trace
    from repair_score import score_group
    cfg=read(ROOT/'configs/repair_final_baseline.json');agent,runtime=load_model(cfg);editor=Dispatch(agent.action_head);checks=[]
    versions={k:p._version for k,p in agent.named_parameters()}
    for row in panel[:2]:
        features,_,meta=load_features(row,cfg)
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']));records=[dict(arm='baseline',trajectory=chain['trajectory'].tolist())]
            for a in arms:
                pred,edit=editor.predict(chain,a);again,_=editor.predict(chain,a);assert np.array_equal(pred,again)
                records.append(dict(arm=a['id'],trajectory=pred.tolist(),edit=edit))
        scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=row['metric_sha256'],scoring=cfg['scoring'],records=records))
        checks.append(dict(token=row['token'],feature_sha256=meta['feature_sha256'],records=scored))
    editor.close();assert versions=={k:p._version for k,p in agent.named_parameters()}
    atomic(OUT/'FINAL_TEST_SMOKE.json',dict(status='PASS',time=stamp(),lock_sha256=sha(path),runtime=runtime,checks=checks))
    # Locked whole-training-pool coverage is descriptive, never used to alter this selection.
    full_tasks=stage(ROOT/'runs'/RUN,'navtrain_full_locked',read(ROOT/'manifests/natural_s0.json'),selected,[0,1,2],chunk=8)
    atomic(OUT/'FULL_TRAIN_READY.json',dict(status='FROZEN_AFTER_SELECTION',time=stamp(),tasks=full_tasks,cases=103288,arms=len(selected),
        seeds=[0,1,2],selection_sha256=sha(OUT/'BEHAVIOR_SELECTION_LOCK.json'),purpose='full coverage, fixed-S0 failures and original-success damage; fitted population, not independent evaluation',changes_selection=False))
    tasks=stage(ROOT/'runs'/RUN,'final_test',panel,arms,[0,1,2,3,4],chunk=8)
    atomic(OUT/'FINAL_TEST_READY.json',dict(status='PASS',time=stamp(),tasks=tasks,cases=len(panel),arms=len(arms),outputs=len(panel)*5*(len(arms)+1),
        lock_sha256=sha(path),smoke_sha256=sha(OUT/'FINAL_TEST_SMOKE.json')))
    print(json.dumps(dict(event='FINAL_TEST_APPENDED',tasks=tasks,arms=len(arms),cases=len(panel))),flush=True)

if __name__=='__main__':main()
