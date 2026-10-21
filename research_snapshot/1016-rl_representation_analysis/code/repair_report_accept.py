"""Static report/source/number/image acceptance. Does not claim browser rendering."""
from common import *
import base64
import io
import re
from html.parser import HTMLParser
from PIL import Image


def main(args):
    setup('repair/report_accept')
    report=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html';text=report.read_text();archive=ROOT/'provenance/report_versions'/args.version
    build=read(archive/'BUILD.json');assert sha(report)==build['report_sha256']
    class Inspect(HTMLParser):
        def __init__(self):super().__init__();self.images=[];self.links=[];self.details=0;self.scripts=0
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='img':self.images.append(a['src'])
            if tag=='a':self.links.append(a)
            if tag=='details':self.details+=1
            if tag=='script':self.scripts+=1
    parsed=Inspect();parsed.feed(text);assert parsed.details>=8 and parsed.scripts==0 and len(parsed.images)>=4
    imageproof=[]
    for src in parsed.images:
        assert src.startswith('data:image/png;base64,');data=base64.b64decode(src.split(',',1)[1]);img=Image.open(io.BytesIO(data));size=img.size;img.verify();imageproof.append(dict(width=size[0],height=size[1],sha256=hashlib.sha256(data).hexdigest()))
    assert not any('download' in a for a in parsed.links)
    assert not re.search(r'>\s*(?:NaN|nan|None|inf)\s*<',text)
    root=ROOT/'repair_v1';lock=read(root/'TEST_LOCK.json');ready=read(root/'FINAL_TEST_READY.json');run=ROOT/'runs'/ready['run']
    for p in [run/'FINAL_ACCEPTANCE.json',run/'independent_rescore/ACCEPTANCE.json',ROOT/'runs'/lock['source_run']/'FINAL_ACCEPTANCE.json']:
        assert read(p)['status']=='PASS'
    summary=read(root/'analysis/final_test/SUMMARY.json');assert summary['coverage_exact']
    for row in summary['summaries']:
        assert f'{row["mean_delta_pdms"]:+.3f}' in text
        assert row['arm']['id'] in text
    assert str(ready['cases']) in text or f'{ready["cases"]:,}' in text
    source=read(ROOT/'configs/repair_final_execution_v1.json')
    for p,h in source['code_sha256'].items():assert sha(ROOT/p)==h,p
    assert build['test_lock_sha256']==sha(root/'TEST_LOCK.json')
    for p,h in lock['fit_sha256'].items():assert sha(ROOT/p)==h
    comparisons=read(root/'analysis/final_test/FINAL_COMPARISONS.json');assert comparisons['protocol_sha256']==sha(root/'FINAL_STATISTICAL_PROTOCOL.json')
    proof=dict(status='PASS',time=stamp(),version=args.version,report_sha256=sha(report),html_static_checked=True,images=imageproof,
        scientific_sources_and_core_numbers_checked=True,fit_and_execution_hashes_unchanged=True,selection_lock_sha256=sha(root/'TEST_LOCK.json'),
        visual_figures_checked=args.figures_reviewed,browser_render_verified=False,resource_release_required=False)
    atomic(archive/'ACCEPTANCE.json',proof)
    if not (ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json').exists():atomic(ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json',proof)
    else:atomic(ROOT/'provenance/LATEST_REPAIR_REPORT_ACCEPTANCE.json',proof)
    print(json.dumps(dict(status='PASS',version=args.version,images=len(parsed.images))),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--figures-reviewed',action='store_true');main(p.parse_args())
