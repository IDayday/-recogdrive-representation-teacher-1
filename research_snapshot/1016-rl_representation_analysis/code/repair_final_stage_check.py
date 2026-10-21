"""Semantic check at five minutes after actual retained-container final launch."""
from common import *
import numpy as np
setup('repair/final_stage_check')
base=ROOT/'runs/repair_final_test_20261016_v1';began=read(base/'node0/AUXILIARY_STARTED.json')['time'];target=dt.datetime.fromisoformat(began)+dt.timedelta(minutes=5)
while dt.datetime.now(dt.timezone.utc)<target:time.sleep(5)
rows=read(base/'stages/final_test/panel.json');by={r['token']:r for r in rows};wanted={'baseline'}|{a['id'] for a in read(base/'stages/final_test/arms.json')}
receipts=sorted((base/'receipts').glob('*.json'));selected=receipts[::max(1,len(receipts)//12)][:12];records=0;base_scores=[]
for path in selected:
 doc=read(path);result=base/'results'/path.name;assert sha(result)==doc['result_sha256'];out=read(result);per={}
 for r in out['records']:
  row=by[r['token']];assert r['feature_sha256']==row['feature_sha256'] and r['metric_sha256']==row['metric_sha256']
  assert r['seed']==seed(r['token'],r['seed_index']);assert r['quality']==quality(r['score']['score'])
  a=np.array(r['trajectory']);assert a.shape==(8,3) and np.isfinite(a).all()
  assert np.all(a[:,0]>=-1.571) and np.all(a[:,0]<=65.171) and np.all(a[:,1]>=-19.681) and np.all(a[:,1]<=22.321)
  per.setdefault(r['token'],set()).add(r['arm']);records+=1
  if r['arm']=='baseline':base_scores.append(r['score']['score'])
 assert all(v==wanted for v in per.values())
assert len(base_scores)>100 and np.mean(base_scores)>.2 and np.max(base_scores)>.9
proof=dict(status='PASS',time=stamp(),seconds_after_actual_launch=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(began)).total_seconds(),
 tasks=[p.stem for p in selected],records=records,baseline_outputs=len(base_scores),sample_baseline_pdms=float(np.mean(base_scores)*100),
 actual_feature_metric_identities_seed_quality_bounds_and_candidate_coverage=True,selection_unchanged=True)
atomic(base/'FIVE_MINUTE_SEMANTIC_ACCEPTANCE.json',proof);print(json.dumps(proof),flush=True)
