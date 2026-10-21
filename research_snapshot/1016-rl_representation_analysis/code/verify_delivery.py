"""Independent delivery audit: read existing outputs; no inference or rescoring run."""
from common import *
import csv
from collections import Counter
import math


def main():
    setup('delivery_verification')
    execution=read(ROOT/'configs/execution.json')
    config=read(ROOT/'configs/baseline.json')
    base=ROOT/'runs'/execution['run_id'];delivery=base/'delivery'
    summary=read(delivery/'summary.json')
    ready=read(base/'BASELINE_READY.json')
    manifest=list(csv.DictReader((ROOT/'manifests/navtrain.csv').open()))
    expected={r['token']:(i,r) for i,r in enumerate(manifest)}
    assert len(expected)==len(manifest)==103288
    assert sha(ROOT/'manifests/navtrain.csv')==config['manifest_sha256']
    for path,value in execution['code_sha256'].items():assert sha(ROOT/path)==value,path
    for item in read(ROOT/'provenance/source_snapshot.json')['files']:
        assert sha(ROOT/item['destination'])==item['sha256'],item['destination']
    assert sha(config['checkpoint'])==config['checkpoint_sha256']
    chunk_hashes=read(delivery/'chunk_sha256.json')
    observed_chunks=set();records={};exit_codes=[]
    dsw=read(ROOT/f'runs/{execution["dsw_smoke_run"]}/dsw_smoke/rank000/runtime.json')
    for rank in range(32):
        root=base/'formal'/f'rank{rank:03d}'
        receipt=read(root/'COMPLETE.json')
        assert receipt['status']=='COMPLETE' and receipt['no_gradients'] and receipt['parameter_versions_unchanged']
        runtime=read(root/'runtime.json')
        for key in ['checkpoint_sha256','planner_dtype','autocast','batch_size','deterministic',
                    'effective_eta','ddim_t','ddim_buffers_sha256','versions','clipping','strict_loaded_tensors']:
            assert runtime[key]==dsw[key],(rank,key)
        panel=[]
        for path in retry(lambda:sorted((root/'chunks').glob('*.json'))):
            data=retry(path.read_bytes)
            name=str(path.relative_to(ROOT));observed_chunks.add(name)
            assert hashlib.sha256(data).hexdigest()==chunk_hashes[name],name
            chunk=json.loads(data);assert chunk['identity']==config['identity']
            for record in chunk['records']:
                token=record['token'];assert token not in records,token
                position,row=expected[token]
                assert position%32==rank==record['rank']
                assert record['valid'] and record['identity']==config['identity']
                assert record['seed']==seed(token) and record['seed_index']==0
                assert record['checkpoint_sha256']==config['checkpoint_sha256']
                assert record['log_name']==row['log_name'] and record['metric_cache']==row['metric_cache']
                assert record['feature_dir']==row['feature_dir']
                poses=record['trajectory']
                assert len(poses)==8 and all(len(point)==3 and all(math.isfinite(v) for v in point) for point in poses)
                values=record['score']
                assert all(math.isfinite(v) and 0<=v<=1 for v in values.values())
                total=values['no_at_fault_collisions']*values['drivable_area_compliance']*(
                      5*values['ego_progress']+5*values['time_to_collision_within_bound']+2*values['comfort'])/12
                assert abs(total-values['score'])<1e-8
                assert quality(values['score'])==record['quality']
                records[token]=record;panel.append(token)
        assert panel==[r['token'] for r in manifest[rank::32]],rank
        assert len(panel)==receipt['completed']==receipt['requested']
    assert observed_chunks==set(chunk_hashes)
    assert set(records)==set(expected) and len(records)==summary['samples']==ready['samples']
    with (delivery/'scores.csv').open() as stream:
        csv_rows=list(csv.DictReader(stream))
    assert len(csv_rows)==len({r['token'] for r in csv_rows})==len(records)
    for row in csv_rows:
        r=records[row['token']]
        assert int(row['seed'])==r['seed'] and row['quality']==r['quality']
        assert float(row['pdms_100'])==r['score']['score']*100
        for key in COMPONENTS:assert float(row[key])==r['score'][key]
    with (delivery/'failure_pool.csv').open() as stream:failures=list(csv.DictReader(stream))
    failed={t for t,r in records.items() if r['score']['score']<.7}
    assert len(failures)==len({r['token'] for r in failures})==len(failed)
    assert {r['token'] for r in failures}==failed
    for r in failures:
        assert float(r['pdms_100'])<70 and float(r['pdms_100'])==records[r['token']]['score']['score']*100
    counts=dict(Counter(r['quality'] for r in records.values()))
    assert counts==summary['quality_counts']==ready['quality_counts']
    mean=math.fsum(r['score']['score']*100 for r in records.values())/len(records)
    assert abs(mean-summary['mean_pdms_100'])<1e-10
    for key in COMPONENTS:
        value=math.fsum(r['score'][key] for r in records.values())/len(records)
        assert abs(value-summary['component_means'][key])<1e-12
    rescored=read(delivery/'independent_rescore.json')
    assert rescored['status']=='PASS'
    assert Path(rescored['import_source']).resolve().is_relative_to(Path(config['shared_reference_source']).resolve())
    assert len(rescored['results'])==summary['independent_rescore_samples']==86
    delta=0.
    for actual in rescored['results']:
        ref=records[actual['token']]
        assert actual['reference_sha256']==ref['reference_sha256'] and actual['metric_sha256']==ref['metric_sha256']
        delta=max(delta,max(abs(actual['score'][k]-ref['score'][k]) for k in actual['score']))
    assert delta==summary['max_rescore_difference']==0
    for node in range(2):
        receipt=read(base/f'node{node}/formal/COMPLETE.json');exit_codes+=receipt['all_worker_exit_codes']
        pods=read(ROOT/f'dlc/final_pods_node{node}.json')['Pods']
        assert len(pods)==1 and pods[0]['Status']=='Succeeded' and pods[0]['StatusDetail']['ExitCode']=='0'
        assert read(ROOT/f'dlc/latest_node{node}.json')['Status']=='Succeeded'
    assert len(exit_codes)==32 and exit_codes==[0]*32
    report=Path(ready['report']);text=report.read_text()
    for value in [f'{mean:.4f}',f'{len(records):,}',*[f'{n:,}' for n in counts.values()]]:assert value in text,value
    assert '<script' not in text.lower()
    output=ROOT/'provenance/FINAL_VERIFICATION.json'
    assert not output.exists(),'Preserve existing verification; use a new evidence path for reruns.'
    result=dict(status='PASS',time=stamp(),run_id=execution['run_id'],samples=len(records),chunks_checked=len(observed_chunks),
                missing=0,duplicates=0,invalid=0,mean_pdms_100=mean,quality_counts=counts,
                all_32_shards_and_seed_mappings_checked=True,all_csv_rows_match=True,complete_failure_pool=True,
                checkpoint_and_execution_hashes_match=True,independent_rescore_samples=len(rescored['results']),
                max_rescore_difference=delta,all_32_worker_exit_codes=exit_codes,both_dlc_jobs_and_pods_succeeded=True,
                report=str(report),report_sha256=sha(report),report_core_numbers_checked=True,browser_render_verified=False,
                verification_scope='read-only audit of completed baseline artifacts; no new inference or experimental extension')
    atomic(output,result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
