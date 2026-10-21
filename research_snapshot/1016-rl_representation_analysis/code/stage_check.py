"""Independent first-stage coverage and saved-trajectory checks, without GPU work."""
from common import *
import csv
import subprocess
from collections import Counter


def main():
    import numpy as np
    setup('independent_stage_check')
    execution=read(ROOT/'configs/execution.json')
    config=read(ROOT/'configs/baseline.json')
    base=ROOT/'runs'/execution['run_id']
    assert read(base/'BOTH_NODE_SMOKE_PASS.json')['status']=='PASS'
    manifest=list(csv.DictReader((ROOT/'manifests/navtrain.csv').open()))
    index={r['token']:(i,r) for i,r in enumerate(manifest)}
    records=[]
    for rank in range(32):
        files=sorted((base/'formal'/f'rank{rank:03d}'/'chunks').glob('*.json'))
        assert files,rank
        for path in files:
            chunk=read(path);assert chunk['identity']==config['identity']
            for record in chunk['records']:
                token=record['token'];position,row=index[token]
                assert position%32==rank==record['rank']
                assert record['seed']==seed(token) and record['seed_index']==0
                assert record['valid'] and record['checkpoint_sha256']==config['checkpoint_sha256']
                assert row['feature_dir']==record['feature_dir'] and row['metric_cache']==record['metric_cache']
                assert row['log_name']==record['log_name']
                assert np.asarray(record['trajectory']).shape==(8,3) and np.isfinite(record['trajectory']).all()
                assert record['quality']==quality(record['score']['score'])
                values=record['score']
                reconstructed=values['no_at_fault_collisions']*values['drivable_area_compliance']*(
                    5*values['ego_progress']+5*values['time_to_collision_within_bound']+2*values['comfort'])/12
                assert abs(reconstructed-values['score'])<1e-8
                records.append(record)
    assert len(records)==len({r['token'] for r in records})
    assert not list((base/'formal').glob('rank*/FAILED.json'))
    selected={r['token']:r for r in sorted(records,key=lambda r:digest(r['token']))[:6]}
    for kind in ['failure','intermediate','high_quality']:
        subset=sorted([r for r in records if r['quality']==kind],key=lambda r:digest(r['token']))[:2]
        selected.update({r['token']:r for r in subset})
    out=ROOT/'provenance/first_stage_check';out.mkdir(parents=True,exist_ok=True)
    tasks=[dict(token=r['token'],trajectory=r['trajectory'],metric_cache=r['metric_cache'],metric_sha256=r['metric_sha256'],scoring=config['scoring'])
           for r in selected.values()]
    atomic(out/'request.json',tasks)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/score.py'),str(out/'request.json'),str(out/'original_scores.json'),
                    '--original-source',config['shared_reference_source']],check=True,timeout=600,cwd=ROOT)
    actual=read(out/'original_scores.json')
    difference=max(abs(a['score'][key]-selected[a['token']]['score'][key]) for a in actual['results'] for key in a['score'])
    assert difference==0
    result=dict(status='PASS',time=stamp(),run_id=execution['run_id'],checked_records=len(records),expected=len(manifest),
                unique_tokens=len({r['token'] for r in records}),active_ranks=32,duplicate_tokens=0,invalid=0,
                seed_mapping_and_shard_membership='PASS',quality_counts=dict(Counter(r['quality'] for r in records)),
                mean_pdms_100=100*sum(r['score']['score'] for r in records)/len(records),
                independent_rescore_samples=len(tasks),max_rescore_difference=difference,
                scope='interim semantic check; not a completed baseline result',test_cache_access=False)
    atomic(out/'acceptance.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
