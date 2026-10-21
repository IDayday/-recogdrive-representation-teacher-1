"""Verify the integrated HTML against immutable experiment/analysis snapshots."""
from common import *
import argparse,base64,io,re,collections
from html.parser import HTMLParser
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

class Document(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[];self.images=[];self.details=0;self.summaries=0;self.downloads=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if tag=='img':self.images.append(a['src'])
        if tag=='details':self.details+=1
        if tag=='summary':self.summaries+=1
        if 'download' in a:self.downloads.append(a)

def image_hashes(document):
    from PIL import Image
    result=[]
    for value in document.images:
        assert value.startswith('data:image/png;base64,'),'Report must remain standalone'
        data=base64.b64decode(value.split(',',1)[1],validate=True)
        with Image.open(io.BytesIO(data)) as image:image.verify()
        with Image.open(io.BytesIO(data)) as image:assert min(image.size)>100
        result.append(hashlib.sha256(data).hexdigest())
    return result

def main(a):
    assert a.figures_reviewed,'Inspect the actual plots before certifying their visual acceptance.'
    setup('vlm_repair/integrated_report_accept')
    latest=read(VOUT/'REPORT_LATEST.json');folder=ROOT/latest['path'];build=read(folder/'BUILD.json')
    canonical=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html'
    assert sha(canonical)==sha(folder/'report.html')==build['report_sha256']==latest['report_sha256']
    assert sha(ROOT/build['source_report'])==build['source_report_sha256']==read(ROOT/'candidate_repair_v1/REPORT_ACCEPTANCE.json')['report_sha256']
    assert sha(ROOT/'code/vlm_integrated_report.py')==build['generator_sha256']
    for path,h in build['snapshot_sha256'].items():assert sha(ROOT/path)==h,path
    body=canonical.read_text();document=Document();document.feed(body)
    assert len(document.ids)==len(set(document.ids))
    assert document.details==document.summaries and not document.downloads
    assert {'upstream-representation-repair','expanded-candidate-repair','repair-oracle-bounds'}.issubset(document.ids)
    for link in document.links:
        assert link,'Empty HTML link'
        if link.startswith('#'):assert link[1:] in document.ids,link
        elif not link.startswith(('https://','http://','mailto:','/mnt/')):
            assert (canonical.parent/link).resolve().exists(),link
    hashes=image_hashes(document);old=Document();old.feed((ROOT/build['source_report']).read_text())
    old_hashes=image_hashes(old);counts=collections.Counter(hashes)
    assert all(counts[h]>=n for h,n in collections.Counter(old_hashes).items())
    for figure in build['figures']:assert sha(ROOT/figure['path'])==figure['sha256'] and figure['sha256'] in counts
    # Match displayed effects, uncertainty and safety ledgers to actual locked
    # outcomes. Do not infer a good repair from the observational AUC panels.
    section=body.split('<section id="upstream-representation-repair">',1)[1].split('</section>',1)[0]
    for row in build['role_records']:
        contrast=row['contrast'];d=row['method']['actual']
        assert f'{contrast["delta_pdms"]:+.4f}' in section
        assert str([round(v,4) for v in contrast['ci95']]) in section
        assert f'Holm p={contrast["p_holm"]:.4g}' in section
        assert f'{d["repaired_above90"]} / {d["high_to_failure"]}' in section
        assert f'{d["collision_net"]:+d} / {d["offroad_net"]:+d} / {d["delta_zero_count"]:+d} / {d["ttc_net"]:+d}' in section
    qda=read(ROOT/build['qda_report_path']);assert len(qda['all_controls'])==84
    for r in qda['all_controls']:
        assert f'{r["cv"]["auc"]:.4f}' in section and f'{r["heldout"]["auc"]:.4f}' in section
    correction=read(ROOT/build['multiplicity_path']);assert correction['all_qda_control_sites_complete']
    dimension=read(ROOT/build['dimension_report_path']);assert dimension['complete']
    for row in dimension['all_frozen_residual_records']:
        cfg=row['spec']['config'];assert f'{cfg["ks"]}/{cfg["kf"]}/{cfg["r"]}' in section
        m=row['confirmation']['metrics'];assert f'{m["auc"]:.4f} / {m["weighted_ap"]:.4f}' in section
    for proof in dimension['source_proofs']:
        assert sha(ROOT/proof['path'])==proof['sha256'] and sha(ROOT/proof['array_path'])==proof['array_sha256']
    for search in correction['searches']:
        assert str(search['completed_cells'])+' / '+str(search['planned_cells']) in section
    assert build['all_requested_full_grid_complete']==all(s['completed_cells']==s['planned_cells'] for s in correction['searches'])
    assert ('尚未在锁定测试中获得' in section)==(not build['supported_primary_ids'])
    assert '未完成不算覆盖' in section and '真实内在维数' in section and '离线PDM评分不等同真实交互闭环' in section
    for marker in [VOUT/'final/SCIENTIFIC_ACCEPTANCE.json',VOUT/'final/BASE_TRAJECTORY_ACCEPTANCE.json',VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json']:
        assert read(marker)['status']=='PASS'
    if build['semantic_complete']:
        assert read(SEM/'repair/SCIENTIFIC_ACCEPTANCE.json')['status']=='PASS'
        assert read(SEM/'repair/BASE_TRAJECTORY_ACCEPTANCE.json')['status']=='PASS'
    for kind in ['scan','rapid']:assert len(list((SEM/kind/'receipts').glob('*.json')))==64
    assert read(SEM/'CACHE_ACCEPTANCE.json')['status']=='PASS'
    result=dict(status='PASS',time=stamp(),report_sha256=sha(canonical),version=folder.name,
        accepted_old_figures_preserved=len(old_hashes),new_figures=len(build['figures']),total_embedded_images=len(hashes),
        figures_visually_reviewed=True,browser_render_verified=False,source_hashes_and_core_numbers_verified=True,
        all_requested_full_grid_complete=build['all_requested_full_grid_complete'],
        no_resource_stop_or_release=True,validator_sha256=sha(Path(__file__)))
    atomic(folder/'ACCEPTANCE.json',result);atomic(VOUT/'REPORT_ACCEPTANCE.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--figures-reviewed',action='store_true');main(p.parse_args())
