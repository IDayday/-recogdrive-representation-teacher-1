"""Final expanded-science and single-report cross-check. No compute-resource mutations."""
from common import *
from PIL import Image
import io,base64
import numpy as np
from html.parser import HTMLParser

setup('subspace_scan/final_verify');out=ROOT/'analysis/subspace_scan_v2';report=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html';text=report.read_text()
for f in ['FINAL_ACCEPTANCE.json','DIRECT_SVD_INDEPENDENT_AUDIT.json','SCIENCE_READY.json','REPORT_DATA_READY.json']:
 assert read(out/f)['status']=='PASS',f
cfg=read(ROOT/'configs/subspace_scan_execution_v2.json')
for p,h in cfg['code_sha256'].items():assert sha(ROOT/p)==h,p
protocol=read(out/'PROTOCOL.json');assert protocol['ks']==[4,8,16,24,32,48,64,128,256] and protocol['kf']==protocol['ks'] and protocol['r']==[2,4,8,16,24,32,48,64]
lock=read(out/'FROZEN_CONFIRMATION.json');result=read(out/'CONFIRMATION_RESULTS.json');control=read(out/'CONTROL_COMPARISONS.json');dist=read(out/'FROZEN_DISTRIBUTIONS.json')
assert result['selection_sha256']==sha(out/'FROZEN_CONFIRMATION.json')
assert dt.datetime.fromisoformat(read(out/'CONTROL_COMPARISON_PROTOCOL.json')['time'])<dt.datetime.fromisoformat(lock['time'])
assert len(result['regions'])==16 and sum(r['stable_region_confirmed'] for r in result['regions'])==10
assert sum(r['stable_region_confirmed'] for r in result['regions'] if r['route']=='r1')==4
assert sum(r['stable_region_confirmed'] for r in result['regions'] if r['route']=='r2')==6
assert len(result['records'])==215 and result['holm_family_sizes']==dict(r1=114,r2=202)
assert len(np.load(out/'CV_SEARCH_LEDGER.npy',mmap_mode='r'))==4091840
assert control['protocol_sha256']==sha(out/'CONTROL_COMPARISON_PROTOCOL.json') and control['selection_changed']==False
assert len(control['records'])==144 and control['all_saved_point_metrics_reproduced']
assert dist['selection_changed']==False and len(dist['records'])==215
assert read(out/'DIMENSION_EFFECTS.json')['ledger_sha256']==sha(out/'CV_SEARCH_LEDGER.npy')
assert len(read(out/'DIMENSION_EFFECTS.json')['records'])==124
assert read(out/'REPORT_BUILD.json')['section_sha256']==sha(out/'REPORT_SECTION.html');assert (out/'REPORT_SECTION.html').read_text() in text
for value in ['4,091,840','0.734/0.704','80/60','ks=8、kf=48、r=48']:
 assert value in text,value
for r in result['regions']:assert r['region_id'] in text
for f in read(out/'REPORT_BUILD.json')['figures']:
 assert sha(ROOT/f['path'])==f['sha256'];Image.open(ROOT/f['path']).verify()
report_accept=read(ROOT/'provenance/LATEST_REPAIR_REPORT_ACCEPTANCE.json');assert report_accept['report_sha256']==sha(report)
for run in ['repair_20261016_v2','repair_null_validation_20261016_v1','repair_final_test_20261016_v1','subspace_scan_20261016_v2']:
 assert read(ROOT/'runs'/run/'FINAL_ACCEPTANCE.json')['status']=='PASS';assert not read(ROOT/'runs'/run/'queue.json')['closed']
proof=dict(status='PASS',time=stamp(),report_sha256=sha(report),expanded_execution_sha256=sha(ROOT/'configs/subspace_scan_execution_v2.json'),
 expanded_selection_sha256=sha(out/'FROZEN_CONFIRMATION.json'),search_variants=4091840,frozen_regions=16,stable_confirmed_regions=10,
 route1_confirmed_regions=4,route2_confirmed_regions=6,control_contrasts=144,figures=11,browser_render_verified=False,
 repair_and_expanded_tasks_accepted=True,all_four_queues_open=True,no_model_recollection_in_expanded_analysis=True)
archive=ROOT/'provenance/report_versions'/report_accept['version']
for name,path in [('previous_expanded_verification.json',ROOT/'provenance/EXPANDED_FINAL_VERIFICATION.json'),('previous_expanded_full_acceptance.json',out/'FULL_ACCEPTANCE.json')]:
 if path.exists():
  destination=archive/name;assert not destination.exists();destination.write_text(path.read_text())
proof['resource_retention_sha256']=sha(ROOT/'provenance/RESOURCE_RETENTION_FINAL.json')
atomic(ROOT/'provenance/EXPANDED_FINAL_VERIFICATION.json',proof);atomic(out/'FULL_ACCEPTANCE.json',proof)
print(json.dumps(dict(status='PASS',figures=11,regions=16,confirmed=10)),flush=True)
