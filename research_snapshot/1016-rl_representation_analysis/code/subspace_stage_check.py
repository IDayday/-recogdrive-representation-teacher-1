"""Real 5-minute crossfit semantic inspection, independent of elapsed preparation time."""
from common import *
import numpy as np
setup('subspace_scan/stage_check');cfg=read(ROOT/'configs/subspace_scan_execution_v2.json');base=ROOT/'runs'/cfg['run']
while not (base/'node0/SMOKE_PASS.json').exists():time.sleep(5)
began=dt.datetime.fromisoformat(read(base/'node0/SMOKE_PASS.json')['time'])
while (dt.datetime.now(dt.timezone.utc)-began).total_seconds()<300:time.sleep(5)
paths=sorted((base/'receipts').glob('cv_*.json'));picked=[]
for route in ['r1','r2']:
 chosen=[p for p in paths if read(p)['task']['route']==route]
 picked+=chosen[::max(1,len(chosen)//6)][:6]
summary=[]
for path in picked:
 receipt=read(path);out=base/'results'/path.name;assert sha(out)==receipt['result_sha256'];doc=read(out);assert not doc['heldout_validation_evaluated'];assert len(doc['search'])==1346
 task=doc['task']
 if task['route']=='r1':assert doc['full_moment_reuse_verified_all_dimensions']
 for r in doc['search']:
  c=r['config'];assert len(r['folds'])==5
  if c['kind']=='residual' and r['status']=='VALID':
   assert all(c['ks']<=f['rank']['rank_success'] and c['kf']<=f['rank']['rank_failure'] and c['r']<=f['rank']['residual_rank'] for f in r['folds'])
  for field in ['P0','P1']:
   m=r.get(field)
   if m is None:continue
   assert 0<=m['auc']<=1 and 0<=m['ap']<=1 and np.isfinite(m['standardized_gap'])
   if task['route']=='r2':assert m['ap_prevalence']==.5 and 0<=m['pair_ordering']<=1
 summary.append(dict(cell=doc['cell'],valid_variants=sum(r['status']=='VALID' for r in doc['search']),requested=1346,sha256=sha(out)))
assert len(summary)>=10
for rank in range(32):
 runtime=read(base/'runtime'/f'rank{rank:03d}.json');assert runtime['backend']=='device_float64' and not runtime['model_loaded'] and runtime['cpu_threads_per_worker']==8
atomic(base/'ACTUAL_CV_5MIN_ACCEPTANCE.json',dict(status='PASS',time=stamp(),seconds_after_real_smoke=(dt.datetime.now(dt.timezone.utc)-began).total_seconds(),checks=summary,all_32_rank_runtime_checked=True))
print(json.dumps(dict(status='PASS',cells=len(summary))),flush=True)
