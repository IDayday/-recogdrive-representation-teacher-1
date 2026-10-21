"""Independent DSW engineering checks before admitting formed-candidate code.

Original batch-two evaluation is imported unchanged, with only its output root
and atomic writer redirected into this task's private engineering directory.
Legacy edits are checked against the original cached-noise continuation.
"""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import traceback


def main(a):
    setup('formed_smoke/'+a.name);compatibility()
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from repair_engine import baseline_row,trace,Editor
    from candidate_repair_engine import CandidateEditor
    from repair_score import score_group
    from r3_runtime import init_scorer
    from r3_formed_scene_v1 import Scene
    from r3_first42_rollout_v2 import save_arrays
    from r3_inference_cache_v2 import constant_context
    import r2_frozen_policy_pack_v2 as original

    dest=ROOT/'runs/formed_engineering_v1'/a.name;assert not (dest/'PASS.json').exists()
    catalog=read(ROOT/'manifests/FORMED_CATALOG_DRAFT_V2.json');entries=catalog['entries']
    selected=[]
    for kind in ['batch2_learned','batch2_delta','batch2_analytic']:
        selected.append(next(e for e in entries if e['kind']==kind))
    for kind in ['batch1_upstream']:
        own=[e for e in entries if e['kind']==kind]
        selected.append(own[0]);selected.append(next(e for e in own if e['definition']['arm']['gate']=='external_observation_qda_hard'))
    selected.extend(e for e in entries if e['kind']=='batch1_action_or_postprocess')
    policies=[]
    for kind in ['hard','candidate','token','finite']:
        policies.append(next(e for e in entries if e['kind']=='batch2_policy_'+kind))
    for flavor in ['soft_joint','hard_continuous']:
        policies.append(next(e for e in entries if e['kind']=='batch2_policy_joint' and e['semantic']['model_kind']==flavor))
    selected+=policies
    atomic(dest/'CONFIG.json',dict(time=stamp(),indices=[60,1],seeds=list(range(5)),entries=selected,
           source_sha256=sha(Path(__file__)),scene_runtime_sha256=sha(ROOT/'code/r3_formed_scene_v1.py'),
           original_evaluator_sha256=sha(BATCH2/'code/r2_frozen_policy_pack_v2.py')))
    engine=Engine();rows_path=BATCH1/'manifests/natural_s0.json';rows=read(rows_path);checks=[]
    original.ROOT=ROOT;original.atomic=atomic
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        # Original complete-policy generator supplies an independent trajectory
        # and independent score reference for every newly adapted policy class.
        references={}
        for entry in policies:
            kind=entry['kind'].removeprefix('batch2_policy_');definition=entry['definition']
            policy_path=BATCH2/definition['policy_path']
            pack_path=dest/'original_inputs'/(entry['id']+'_PACK.json')
            pack=dict(policies=[dict(id=entry['id'],kind=kind,policy=str(policy_path),policy_sha256=definition['policy_sha256'])],include_raw_experts=True)
            atomic(pack_path,pack)
            lock_path=pack_path.with_name(entry['id']+'_LOCK.json')
            atomic(lock_path,dict(pack_sha256=sha(pack_path),rows_sha256=sha(rows_path),authorized_modes=['engineering'],status='ENGINEERING_ONLY'))
            task=dict(id=entry['id'],stage=str((dest/'original_outputs').relative_to(ROOT)),lock=str(lock_path),lock_sha256=sha(lock_path),pack=str(pack_path),pack_sha256=sha(pack_path),rows=str(rows_path),rows_sha256=sha(rows_path),mode='engineering',panel=[60,1],start=0,end=2,seeds=list(range(5)),reference_mode='navtrain_archive')
            result=original.run(engine,task,pool)
            records=read(ROOT/result['path'])['records']
            references[entry['id']]={(r['token'],r['seed_index']):r for r in records if r['arm']==entry['id']}
            atomic(dest/'LIVE.json',dict(status='ORIGINAL_POLICY_GOLDEN_COMPLETE',time=stamp(),policy=entry['id']))
        for index in [60,1]:
            row=rows[index];features=raw_features(row);reference=baseline_row(row);arrays={};uncached={};annotations=[];tensors=[]
            with torch.no_grad():
                scene=Scene(engine,features,row['token'])
                for entry in [dict(id='Base',kind='Base',definition={})]+selected:
                    for j in range(5):
                        branch=scene.evaluate(entry,j);value=branch.trajectory.cpu().numpy()
                        h=branch.interface[0,engine.inputs['attention_mask'][0].bool()].float().cpu().numpy()
                        key=entry['id']+'_S'+str(j);arrays[key]=h;uncached[key]=(value.copy(),h.copy())
                        if entry['id']=='Base' and j==0:assert np.array_equal(value,reference['trajectory'])
                        if entry['id'] in references:assert value.tolist()==references[entry['id']][(row['token'],j)]['trajectory']
                        tensors.append(value);annotations.append(dict(arm=entry['id'],seed_index=j,relative_edit=branch.relative_edit,interface_key=key))
                # The inference cache is not admitted just because a small CPU
                # contract test passed. Compare real trajectories AND interfaces.
                with constant_context(engine,verify=False) as cache_stats:
                    cached=Scene(engine,features,row['token'])
                    for entry in [dict(id='Base',kind='Base',definition={})]+selected:
                        for j in range(5):
                            branch=cached.evaluate(entry,j);key=entry['id']+'_S'+str(j)
                            value=branch.trajectory.cpu().numpy();h=branch.interface[0,engine.inputs['attention_mask'][0].bool()].float().cpu().numpy()
                            assert np.array_equal(value,uncached[key][0]),('cache_trajectory',key)
                            assert np.array_equal(h,uncached[key][1]),('cache_interface',key)
                # Compare each legacy full-forward edit with the historical
                # continuation, including its original paired native noises.
                for j in range(5):
                    prepared={k:v for k,v in features.items() if k not in ['pixel_values','last_hidden_state']}
                    prepared['last_hidden_state']=scene.hidden.squeeze(0)
                    chain=trace(engine.agent,prepared,seed(row['token'],j))
                    for entry in selected:
                        if entry['kind']!='batch1_action_or_postprocess':continue
                        arm=entry['definition']['arm'];actual=arm['legacy_arm'] if arm['method']=='legacy' else arm
                        if arm['method']=='trajectory_scale':
                            from repair_postprocess import scale_trajectory
                            value=scale_trajectory(chain['trajectory'],arm['factor'])
                        else:
                            editor=CandidateEditor(engine.agent.action_head) if ('fit' in actual or 'components' in actual) else Editor(engine.agent.action_head)
                            try:value,metrics=editor.predict(chain,actual)
                            finally:editor.close()
                        assert np.array_equal(value,uncached[entry['id']+'_S'+str(j)][0]),('legacy_continuation',entry['id'],j)
            records=[dict(annotation,trajectory=value.tolist()) for annotation,value in zip(annotations,tensors)]
            scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=3600)
            for record in scored:
                if record['arm']=='Base' and record['seed_index']==0:assert record['score']==reference['score']
                if record['arm'] in references:assert record['score']==references[record['arm']][(row['token'],record['seed_index'])]['score']
            path=dest/(row['token']+'.npz');hashed=save_arrays(path,arrays)
            atomic(dest/(row['token']+'.json'),dict(status='PASS_CASE',time=stamp(),records=scored,interface_path=str(path.relative_to(ROOT)),interface_sha256=hashed,cache_statistics=cache_stats,all_interfaces_from_actual_execution=True))
            checks.append(dict(token=row['token'],records=len(scored),all_original_policy_trajectories_and_scores_exact=True,all_legacy_continuations_exact=True,cache_trajectories_and_interfaces_exact=True));engine.verify_engine()
            atomic(dest/'LIVE.json',dict(status='CASE_COMPLETE',time=stamp(),checks=checks))
    atomic(dest/'PASS.json',dict(status='PASS_DSW_SINGLE_DEVICE_ENGINEERING',time=stamp(),checks=checks,physical_devices=1,not_multi_device_admission=True,formal_expansion_not_started=True))
    print(json.dumps(dict(event='FORMED_SINGLE_DEVICE_ENGINEERING_PASS',checks=checks)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',default='dsw_v1');a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/formed_engineering_v1'/a.name/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
