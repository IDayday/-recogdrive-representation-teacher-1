"""Check the delivered HTML, captured evidence and documented completion."""
from r2_common import *
from html.parser import HTMLParser
import base64
import re


class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.column=0;self.header=[];self.tables=0
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag=='table':self.header=[];self.tables+=1
        elif tag=='tr':self.column=0
        elif tag in ['th','td']:
            alignment=attributes.get('class','')
            if tag=='th':self.header.append(alignment)
            else:assert self.column<len(self.header) and alignment==self.header[self.column]
            self.column+=1


def main():
    setup('report_delivery_acceptance',threads=2)
    build_path=max((ROOT/'provenance/report_builds').glob('scientific_v4_*.json'))
    build=read(build_path);report=Path(build['report']);assert build['formal'] and sha(report)==build['report_sha256']
    assert sha(ROOT/'code/r2_report_batch2_v4.py')==build['builder_source_sha256']
    assert sha(ROOT/'code/r2_report_confirmed_sections_v1.py')==build['helper_source_sha256']
    for item in build['sources']:assert sha(ROOT/item.get('snapshot',item['path']))==item['sha256']
    protocols=read(ROOT/'provenance/REPORT_PROTOCOL_SNAPSHOTS.json');assert protocols['report_sha256']==build['report_sha256']
    for item in protocols['protocols']:assert sha(ROOT/item['snapshot'])==item['sha256']
    page=report.read_text();parser=Tables();parser.feed(page)
    assert '正式验收报告' in page and '进行中的证据快照' not in page
    assert '自然验证尚未完成' not in page and '最终测试尚未完成' not in page
    for value in ['1.55884','1.33668','0.09192','17,475','12,146','4,549','538','每个噪声分别满足','联合监督']:
        assert value in page,value
    images=re.findall(r'data:image/png;base64,([^"\s]+)',page);assert len(images)==6
    assert all(base64.b64decode(v).startswith(b'\x89PNG\r\n\x1a\n') for v in images)
    assert not re.search(r'\bdownload=|<script[^>]+src=',page)
    science=read(ROOT/'provenance/FINAL_SCIENTIFIC_ACCEPTANCE.json');assert science['status']=='PASS'
    for item in science['proofs']:assert sha(ROOT/item['path'])==item['sha256']
    selection=read(ROOT/'provenance/final_confirmation/SELECTION.json')
    validation=read(ROOT/'runs/frozen_natural_validation_batch2_three_roles_v1/SUBMISSION.json')
    test=read(ROOT/'runs/frozen_natural_test_batch2_three_roles_v1/SUBMISSION.json')
    assert selection['time']<validation['time']<test['time']
    complete=ROOT/'STUDY_COMPLETE.md';assert complete.exists()
    for target in re.findall(r'\]\(([^)]+)\)',complete.read_text()):
        if target.startswith('https://'):continue
        assert (complete.parent/target.split('#')[0]).resolve().exists(),target
    navigation=ROOT.parent/'doc/研究导航.md';text=navigation.read_text()
    assert text.count('### 1018-representation_repair_batch2')==1 and str(report.relative_to(ROOT.parent/'doc')) in text
    plan=read_text=(ROOT/'PLAN.md').read_text()
    assert all('- [x] '+phase+'：' in plan for phase in ['C–D','E','F','G'])
    target=ROOT/'provenance/FINAL_DELIVERY_ACCEPTANCE.json';assert not target.exists()
    atomic(target,dict(status='PASS_FORMAL_REPORT_AND_IMMUTABLE_EVIDENCE',time=stamp(),
        report=str(report),report_sha256=sha(report),report_build=str(build_path.relative_to(ROOT)),
        captured_source_json_and_image_entries=len(build['sources']),protocol_snapshots=len(protocols['protocols']),
        science_proofs_checked=len(science['proofs']),HTML_tables_alignment_checked=parser.tables,
        embedded_PNGs_valid=6,all_six_standalone_scientific_figures_actually_viewed=True,
        full_browser_visual_validation=False,completed_study_links_checked=True,
        PLAN_sha256=sha(ROOT/'PLAN.md'),navigation_sha256=sha(navigation),study_entry_sha256=sha(complete),
        resources_retained=True,no_StopJob_or_global_queue_closure=True,
        source_sha256=sha(Path(__file__))))
    print(json.dumps(dict(status='PASS',report=str(report),tables=parser.tables,sources=len(build['sources']),protocols=len(protocols['protocols']),figures=6)))


if __name__=='__main__':main()
