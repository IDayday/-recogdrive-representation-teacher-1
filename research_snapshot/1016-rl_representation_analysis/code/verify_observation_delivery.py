"""Read-only final observation audit plus a new immutable receipt."""
from common import *
import argparse
import csv
from html.parser import HTMLParser
import numpy as np


class Document(HTMLParser):
    def __init__(self):super().__init__();self.images=[];self.links=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img':self.images.append(a.get('src',''))
        if tag=='a':self.links.append(a.get('href',''))
    def handle_data(self,data):self.text.append(data)


def main(args):
    run=ROOT/'runs'/args.run;analysis=ROOT/'analysis/observation_v1';temporal=ROOT/'analysis/temporal_v1'
    assert not args.output.exists()
    cfg=read(ROOT/'configs/paired_execution_v2_16card.json')
    baseline=read(ROOT/'configs/execution.json')
    for spec in [baseline,cfg]:
        for p,h in spec['code_sha256'].items():assert sha(ROOT/p)==h,p
    refs=read(ROOT/'runs/gt_reference_full_20261016_v2/references.json')
    failures=list(csv.DictReader((ROOT/'runs'/baseline['run_id']/'delivery/failure_pool.csv').open()))
    assert {r['token'] for r in refs}=={r['token'] for r in failures} and len(refs)==2288
    assert all(r['eligible'] and r['exclusion_reason'] is None for r in refs)
    assert sum(r['gt_score']['score']<=.9 for r in refs)==432
    bysubset={s:{r['session'] for r in refs if r['subset']==s} for s in ['exploration','validation']}
    assert bysubset['exploration'].isdisjoint(bysubset['validation'])
    a=read(run/'formal_acceptance/ACCEPTANCE.json');assert a['status']=='PASS'
    assert a['scenes']==2288 and a['candidates']==45760 and a['arrays']==22880
    assert a['original_gt_not_gt90_scenes_retained']==432 and a['independent_score_max_delta']==0
    assert read(run/'pilot_acceptance/ACCEPTANCE.json')['all_anchor_tensors_and_outputs_exact']
    workers=read(run/'formal_WORKERS_COMPLETE.json');assert workers['exit_codes']==[0]*16
    assert read(run/'MONITOR_COMPLETE.json')['cloud']['Status']=='Succeeded'
    cloud=read(ROOT/'dlc/paired_16card_final.json')
    assert cloud['Status']=='Succeeded' and len(cloud['Pods'])==1
    assert cloud['Pods'][0]['Status']=='Succeeded' and cloud['Pods'][0]['StatusDetail']['ExitCode']=='0'
    assert read(ROOT/'dlc/paired_8card_final_stopped.json')['Status']=='Stopped'
    low=read(analysis/'COMPLETE.json');assert low['status']=='COMPLETE' and low['cells']==152 and low['primary_family']==304
    assert read(temporal/'COMPLETE.json')['pairs']==22880
    p=read(analysis/'primary_tests.json');s=read(analysis/'secondary_tests.json')
    assert len(p)==304 and len(s)==1216
    for r in p+s:
        assert r['n']>0 and r['sessions']>0 and 0<=r['ordering']<=1
        assert 0<=r['p']<=1
        assert 0<=r.get('q_fdr',r.get('q_fdr_secondary'))<=1
        assert len(r['ci95'])==2 and all(0<=v<=1 for v in r['ci95'])
    for f in (analysis/'cells').glob('*.npz'):
        with np.load(f,allow_pickle=False) as data:assert all(np.isfinite(data[k]).all() for k in data.files)
    report=Path(args.report);doc=Document();doc.feed(report.read_text())
    assert len(doc.images)==5 and all(x.startswith('data:image/png;base64,') for x in doc.images)
    assert not any(x.startswith(('http://','https://')) for x in doc.links)
    text=' '.join(doc.text)
    for term in ['2,288','45,760','432','304','不提前按GT>90筛除','未做浏览器渲染验收']:assert term in text,term
    from observation_analysis import basis_svd
    sample=read(ROOT/'provenance/analysis_math_smoke.json');assert sample['status']=='PASS'
    # Recompute displayed uncertainty-family counts and feature selection from saved cells.
    cells=[read(f) for f in (analysis/'cells').glob('*.json')]
    assert max(cells,key=lambda c:c['variants'][0]['top8_energy'])['cell']==low['featured_cell']
    assert sum(r['q_fdr']<.05 and r['ordering']>.5 for r in p)==low['primary_significant_positive']
    result=dict(status='PASS',time=stamp(),run=args.run,scenes=2288,candidates=45760,representation_files=22880,
        original_gt_not_gt90_retained=432,exploration_validation_sessions_disjoint=True,
        all_16_workers_exit_zero=True,job_and_pod_succeeded=True,prior_8card_job_stopped=True,
        lowdim_cells=len(cells),primary_tests=len(p),secondary_tests=len(s),all_projection_artifacts_finite=True,
        baseline_frozen_code_unchanged=True,paired_execution_code_unchanged=True,
        report=str(report.resolve()),report_sha256=sha(report),embedded_figures=len(doc.images),
        browser_render_verified=False,repair_performed=False,test_cache_access=False,
        analysis_code_sha256={f:sha(ROOT/'code'/f) for f in ['observation_analysis.py','temporal_observation.py','observation_report.py','verify_observation_delivery.py']})
    atomic(args.output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--report',required=True)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args();setup('observation_final_audit');compatibility();main(a)
