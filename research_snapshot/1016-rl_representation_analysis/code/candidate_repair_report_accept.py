"""Static report/source/image acceptance after scientific acceptance and manual figure review."""
from common import *
import argparse
import base64
import io
import re
from html.parser import HTMLParser
from candidate_repair_fit import OUT

class Document(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[];self.images=[];self.details=0;self.summaries=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if tag=='img':self.images.append(a['src'])
        if tag=='details':self.details+=1
        if tag=='summary':self.summaries+=1

def main(args):
    from PIL import Image
    assert args.figures_reviewed,'Review actual plot files before marking visual acceptance'
    setup('candidate_repair/report_accept')
    latest=read(OUT/'LATEST_REPORT.json');archive=ROOT/latest['path'];build=read(archive/'BUILD.json')
    canonical=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html'
    assert sha(canonical)==latest['report_sha256']==build['report_sha256']==sha(archive/'report.html')
    assert read(OUT/'FINAL_ACCEPTANCE.json')['status']=='PASS'
    assert sha(OUT/'FINAL_ACCEPTANCE.json')==build['acceptance_sha256']
    assert sha(OUT/'analysis/final_test/FINAL_STATISTICS.json')==build['statistics_sha256']
    source=OUT/'report_versions/SOURCE_REPORT.html';assert sha(source)==build['source_report_sha256']
    assert sha(source)==read(ROOT/'provenance/STATUS_before_candidate_repair.json')['report_sha256']
    # The already-accepted observation/first-repair figures stay unchanged in the integrated document.
    original=Document();original.feed(source.read_text());parser=Document();body=canonical.read_text();parser.feed(body)
    assert len(set(parser.ids))==len(parser.ids) and parser.details==parser.summaries
    for link in parser.links:
        if link.startswith('#'):assert link[1:] in parser.ids
    assert 'expanded-candidate-repair' in parser.ids
    assert not re.search(r'<(?:a|button)[^>]*\bdownload\b',body,re.I)
    hashes=[]
    for item in parser.images:
        assert item.startswith('data:image/png;base64,');raw=base64.b64decode(item.split(',',1)[1]);im=Image.open(io.BytesIO(raw));im.verify()
        im=Image.open(io.BytesIO(raw));assert im.width>100 and im.height>100
        hashes.append(hashlib.sha256(raw).hexdigest())
    original_hashes=[hashlib.sha256(base64.b64decode(x.split(',',1)[1])).hexdigest() for x in original.images]
    assert all(h in hashes for h in original_hashes)
    for figure in build['figures']:assert sha(ROOT/figure['path'])==figure['sha256'] and figure['sha256'] in hashes
    section=body.split('<section id="expanded-candidate-repair">',1)[1].split('</section>',1)[0]
    final=read(OUT/'analysis/final_test/FINAL_STATISTICS.json');lock=read(OUT/'FINAL_TEST_LOCK.json');by={r['arm']:r for r in final['details']}
    for arm in read(OUT/'BEHAVIOR_SELECTION_LOCK.json')['arms']:
        d=by[arm['id']];assert str(d['repaired_gt90']) in section and str(d['high_to_failure']) in section
        delta=f'{d["delta_pdms"]:+.4f}';assert delta in section
    assert '第二轮' in body and '未验证' in body and '五种子' in section
    for group in ['fit_sha256','gate_sha256']:
        for p,h in lock[group].items():assert sha(ROOT/p)==h
    for p,h in read(ROOT/'configs/candidate_repair_execution_v1.json')['code_sha256'].items():assert sha(ROOT/p)==h
    result=dict(status='PASS',time=stamp(),version=latest['version'],report_sha256=sha(canonical),source_report_preserved=True,
        source_figures_unchanged=len(original_hashes),new_figures=len(build['figures']),total_embedded_images=len(hashes),
        core_numbers_and_sources_verified=True,locked_fits_and_runtime_unchanged=True,static_html_checked=True,figures_visually_reviewed=True,
        browser_render_verified=False,generator_sha256=sha(ROOT/'code/candidate_repair_report.py'))
    atomic(archive/'ACCEPTANCE.json',result);atomic(OUT/'REPORT_ACCEPTANCE.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--figures-reviewed',action='store_true');main(p.parse_args())
