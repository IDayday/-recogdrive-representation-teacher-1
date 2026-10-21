"""Independent evidence audit after correcting the two routes' data definitions."""
from common import *
import argparse
from collections import Counter
import csv
from html.parser import HTMLParser
import numpy as np


class HTML(HTMLParser):
    def __init__(self):super().__init__();self.images=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='img':self.images.append(dict(attrs).get('src',''))
    def handle_data(self,data):self.text.append(data)


def audit(args):
    execution=read(ROOT/'configs/natural_execution_v1.json');base=ROOT/'runs'/execution['run']
    r1=ROOT/'analysis/natural_route1_v1';r2=ROOT/'analysis/paired_route2_completion_v2';protocol=read(ROOT/'configs/natural_route1_v1.json')
    assert not args.output.exists()
    for spec in [read(ROOT/'configs/execution.json'),execution,read(ROOT/'configs/natural_analysis_execution_v1.json'),read(ROOT/'configs/natural_analysis_execution_v2.json')]:
        for p,h in spec['code_sha256'].items():assert sha(ROOT/p)==h,p
    assert protocol['route']=='route_one_natural_model_success_failure' and not protocol['gt_initialization']
    assert not protocol['paired_route2_candidates']
    manifest=read(ROOT/'manifests/natural_s0.json');assert len(manifest)==103288
    scores=list(csv.DictReader((ROOT/'runs'/protocol['baseline_run']/'delivery/scores.csv').open()))
    assert [r['token'] for r in manifest]==[r['token'] for r in scores]
    seen=set();counts=Counter();records=[];chunks=sorted((base/'formal').glob('rank*/chunks/*.json'));assert len(chunks)==3232
    projected=sorted((r1/'projected_chunks').glob('*.json'));assert len(projected)==3232
    hash_receipts={r['source_chunk']:r for r in map(read,projected)}
    for path in chunks:
        document=read(path)
        assert document['identity']==protocol['identity']
        proof=hash_receipts[str(path)];assert proof['source_hash_verified']
        assert proof['source_array_sha256']==document['array_sha256']
        for r in document['records']:
            i=r['global_index'];m=manifest[i];s=scores[i]
            assert r['token']==m['token']==s['token'] and i not in seen;seen.add(i)
            assert r['source']=='natural_model_S0' and not r['gt_initialization']
            assert r['exact_baseline_trajectory_replay'] and r['seed']==seed(r['token'])==int(s['seed'])
            assert r['feature_sha256']==s['feature_sha256'] and r['quality']==quality(r['score']['score'])==s['quality']
            assert abs(100*r['score']['score']-float(s['pdms_100']))<1e-10
            counts[(r['subset'],r['quality'])]+=1;records.append(r)
    assert seen==set(range(103288))
    assert counts==Counter((r['subset'],r['quality']) for r in manifest)
    for subset in ['exploration','validation']:
        for label in ['high_quality','failure','intermediate']:
            values=np.asarray([r['score']['score'] for r in records if r['subset']==subset and r['quality']==label],dtype=np.float64)
            group=r1/'moments'/f'{subset}__{label}'
            assert int(np.load(group/'n.npy'))==len(values)
            assert np.allclose(float(np.load(group/'sum_y.npy')),values.sum(),rtol=1e-11,atol=1e-9)
            assert np.allclose(float(np.load(group/'sum_y2.npy')),values@values,rtol=1e-11,atol=1e-9)
    totals=Counter(r['quality'] for r in records);assert dict(totals)==dict(high_quality=90153,failure=2288,intermediate=10847)
    assert read(base/'BOTH_NODE_SMOKE_PASS.json')['anchors_compared']==96
    for node in range(2):
        receipt=read(base/f'node{node}/formal_COMPLETE.json');assert receipt['exit_codes']==[0]*16
        cloud=read(ROOT/f'dlc/natural_final_node{node}.json')
        assert cloud['Status']=='Succeeded' and len(cloud['Pods'])==1
        assert cloud['Pods'][0]['Status']=='Succeeded' and cloud['Pods'][0]['StatusDetail']['ExitCode']=='0'
    one=read(r1/'COMPLETE.json');two=read(r2/'COMPLETE.json')
    assert one['route']=='route1_natural_model_S0' and one['natural_population']==103288
    assert one['cells']==760 and one['primary_tests']==1520 and not one['gt_initialization']
    assert two['route']=='route2_failure_GT_pairs_only' and not two['route1_data_used'] and two['cells']==152
    tests=read(r1/'tests.json');assert len(tests)==1520
    assert {t['step_t'] for t in tests}=={80,60,40,20,0}
    for t in tests:
        assert t['natural_source'] and not t['gt_initialization']
        for name in ['failure_auc','failure_average_precision','shared_training_bin_overlap','p','q_fdr']:assert 0<=t[name]<=1
        assert t['validation_success']==15253 and t['validation_failure']==438
        assert t['within_session_contrast_sessions']>=8
        assert np.isfinite(t['continuous_pdms_mae_100']) and np.isfinite(t['mse_ratio_to_constant'])
    assert read(r1/'PROJECTIONS_READY.json')['all_raw_chunk_hashes_verified']
    assert read(r1/'PROJECTIONS_READY.json')['independent_raw_tile_moments_match']
    # Independently compare projected empirical means/covariances with exact full-population moment predictions.
    metadata=read(r1/'metadata.json');labels=np.asarray([r['quality'] for r in metadata]);train=np.asarray([r['subset']=='exploration' for r in metadata])
    for step,layer,token in [(0,0,0),(4,17,7),(2,18,3)]:
        cell=read(r1/'cells'/f'step{step}_layer{layer:02d}_token{token}.json')
        x=np.load(r1/('coordinates_hidden.npy' if layer<18 else 'coordinates_output.npy'),mmap_mode='r')
        value=np.asarray(x[:,step,layer,token] if layer<18 else x[:,step,token],dtype=np.float64)
        with np.load(r1/'cells'/f'step{step}_layer{layer:02d}_token{token}.npz',allow_pickle=False) as b:
            for ci,name in enumerate(['uncentered','pooled_centered']):
                center=b[f'{name}_center']@b[f'{name}_residual_basis'];z=value[:,ci*8:ci*8+8]-center
                for label in ['high_quality','failure']:
                    observed=z[train&(labels==label)];wanted=cell['variants'][ci]['distributions']['exploration'][label]
                    assert np.allclose(observed.mean(0),wanted['mean'],rtol=3e-5,atol=3e-6),(step,layer,token,name,label,'mean')
                    assert np.allclose(np.cov(observed,rowvar=False),wanted['covariance'],rtol=3e-5,atol=3e-6),(step,layer,token,name,label,'covariance')
    # Route2 cases must be the original natural failures, and must never substitute for natural successes.
    refs=read(ROOT/'runs/gt_reference_full_20261016_v2/references.json')
    assert {r['token'] for r in refs}=={r['token'] for r in records if r['quality']=='failure'}
    mode_tests=read(r2/'mode_transfer_tests.json')
    assert len(mode_tests)==10944 and sum(t['inference_qualified'] for t in mode_tests)==8208
    for file in (r2/'cells').glob('*.json'):
        cell=read(file);assert cell['route']=='route2_failure_GT_pairs_only' and not cell['route1_data_used']
        assert len(cell['summaries'])==5
        assert next(c for c in cell['independent_mode_fit_coverage'] if c['mode']=='progress_only')['status']=='INSUFFICIENT_FINAL_QUALITY_PAIRS'
    report=Path(args.report).resolve();doc=HTML();doc.feed(report.read_text());content=' '.join(doc.text)
    for term in ['90,153成功／2,288失败／10,847中间','不能用路线二的全部候选代替路线一十万级自然输出','1,520','1,733','184','115']:assert term in content,term
    assert len(doc.images)==6 and all(v.startswith('data:image/png;base64,') for v in doc.images)
    assert read(ROOT/'analysis/two_route_report_build.json')['sha256']==sha(report)
    result=dict(status='PASS',time=stamp(),route1_source='full natural S0 model predictions',route1_population=103288,
        route1_success=90153,route1_failure=2288,route1_middle=10847,route1_raw_chunks=3232,all_raw_hashes_checked_during_projection=True,
        all_natural_trajectories_exact_original_baseline_replay=True,route1_gt_initialization=False,
        route1_cells=760,route1_primary_tests=1520,route2_source='2288 natural failures paired with GT, final rescoring',
        route2_candidates=45760,route2_distribution_cells=152,route2_mode_transfer_family=8208,
        datasets_not_substituted=True,full_population_moments_match_independent_raw_and_projection_checks=True,
        all_32_workers_exit_zero=True,both_jobs_and_pods_succeeded=True,report=str(report),report_sha256=sha(report),figures=6,
        original_baseline_and_paired_code_unchanged=True,intervention=False,test_cache_access=False,browser_render_verified=False,
        correction='previously reported route1 candidate-pool analysis is reclassified as route2 control; prior scope claim withdrawn',
        analysis_code_sha256={f:sha(ROOT/'code'/f) for f in ['natural_analysis.py','natural_analysis_v2.py','paired_distribution_completion.py','two_route_report.py','verify_two_routes.py']})
    atomic(args.output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    setup('verify_two_routes');compatibility();audit(a)
