"""Validate actual corrected-span final parents without replacing primary evidence."""
from common import *
import numpy as np
from vlm_core import VOUT,raw_features
from vlm_semantic import SEM
from vlm_intervene_v4 import Engine
from vlm_repair_queue_v6 import Fits
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_semantic_v2/final_engineering');compatibility()
    import torch
    from repair_engine import baseline_row
    from repair_score import score_group
    request=read(SEM/'repair/ENGINEERING_REQUEST.json');arms=request['arms'];e=Engine();f=Fits()
    rows=read(ROOT/'repair_v1/anchors.json')[:2];allrows=read(ROOT/'manifests/natural_s0.json');known={r['token'] for r in rows}
    for a in arms:
        for part in a['parts'] if a['method']=='combination' else [a]:
            original=read(VOUT/'fits'/(part['fit_id']+'.json'));proof=read(ROOT/original['cell_proof_path']);x=np.load(ROOT/proof['path'],mmap_mode='r')
            idx=next(i for i,r in enumerate(allrows) if r['subset']=='exploration' and np.isfinite(x[i,0]))
            if allrows[idx]['token'] not in known:rows.append(allrows[idx]);known.add(allrows[idx]['token'])
    checks=[]
    with torch.no_grad():
        for row in rows:
            raw=raw_features(row);h=e.forward_native(raw);before=baseline_row(row);base=e.trajectory(raw,h,seed(row['token']));assert np.array_equal(base.cpu().numpy(),before['trajectory'])
            records=[dict(arm='baseline',trajectory=base.cpu().numpy().tolist())]
            for a in arms:
                if a['method']=='combination':hidden,post,stat=e.combined(a['parts'],f.get)
                else:edited,stat=e.edited(a,f.get(a));hidden,post=e.suffix(a['block'],edited)
                pred=e.trajectory(raw,hidden,seed(row['token']),post);again=e.trajectory(raw,hidden,seed(row['token']),post)
                assert torch.equal(pred,again) and float(stat[0]/stat[1].clamp(min=1e-12))<=a['cap']+1e-6
                records.append(dict(arm=a['id'],trajectory=pred.cpu().numpy().tolist(),edit=stat.cpu().tolist()))
            scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=before['metric_sha256'],scoring=e.cfg['scoring'],records=records));assert scored[0]['score']==before['score'];e.verify_engine();checks.append(dict(token=row['token'],records=scored))
    atomic(SEM/'repair/ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),checks=checks,repeat_exact=True,caps_actual_native_checked=True,actual_final_parents_and_controls_checked=True,primary_engineering_evidence_unchanged=True))

if __name__=='__main__':main()
