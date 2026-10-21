"""Actual stored representations and full moments, numerical engineering only; no planner."""
from common import *
import io
import numpy as np
from subspace_scan_math import directions
from subspace_scan_cv import mul,original_moments,endpoint


def main():
    setup('subspace_scan/real_smoke')
    assert (ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json').exists()
    backend=read(ROOT/'provenance/SUBSPACE_BACKEND_SMOKE.json')['selected_backend'];manifest=read(ROOT/'manifests/natural_s0.json');by={r['token']:r for r in manifest};samples={384:[],512:[]};sources=[]
    for anchor in read(ROOT/'repair_v1/anchors.json'):
        r=by[anchor['token']];index=r['global_index'];rank=index%32;offset=(index//32)//32*32
        p=ROOT/f'runs/natural_s0_repr_20261016T080905Z/formal/rank{rank:03d}/chunks/{offset:06d}.json';doc=read(p);raw=Path(doc['array_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==doc['array_sha256']
        at=next(i for i,row in enumerate(doc['records']) if row['token']==r['token'])
        with np.load(io.BytesIO(raw),allow_pickle=False) as z:
            assert z['representations'].shape[1:]==(5,18,8,384) and z['dit_output'].shape[1:]==(5,8,512)
            assert np.array_equal(z['trajectory'][at],np.asarray(doc['records'][at]['trajectory'],dtype=np.float32))
            samples[384].append(z['representations'][at,4,6,0]);samples[512].append(z['dit_output'][at,4,0])
        sources.append(dict(path=doc['array_path'],sha256=doc['array_sha256']))
    checks=[]
    meta=read(ROOT/'analysis/observation_v1/cache/metadata.json');q=np.load(ROOT/'analysis/observation_v1/cache/scores.npy');train=np.array([r['subset']=='exploration' for r in meta]);mask=train&endpoint(q[0]);ss=q[0,mask];ii=np.arange(int(mask.sum()))
    for d,layer in [(384,6),(512,18)]:
        task=dict(step=4,layer=layer,token=0);mom=[original_moments(task,label) for label in ['high_quality','failure']]
        h=np.load(ROOT/('analysis/observation_v1/cache/hidden_P0.npy' if d==384 else 'analysis/observation_v1/cache/output_P0.npy'),mmap_mode='r')
        a=np.array(h[mask,:,6,0] if d==384 else h[mask,:,0],dtype=np.float64);hi=a[ii,np.argmax(ss,axis=1)];lo=a[ii,np.argmin(ss,axis=1)]
        for route in ['r1','r2']:
            for centered in [False,True]:
                w,c,rank= directions(None,None,centered,9,moments=mom) if route=='r1' else directions(hi,lo,centered,9)
                valid=np.flatnonzero(np.isfinite(w).all(0));x=np.asarray(samples[d]) if route=='r1' else np.concatenate([hi[:3],lo[:3]])
                reference=mul(x,w[:,valid],c,'cpu_float64');actual=mul(x,w[:,valid],c,backend);diff=float(np.max(np.abs(reference-actual)));assert diff<1e-9
                checks.append(dict(route=route,dimension=d,centered=centered,valid_probes=len(valid),max_difference=diff,
                    class_rank_success=rank[-1]['rank_success'],class_rank_failure=rank[-1]['rank_failure'],requested_main_dimensions_up_to=256,requested_residual_dimensions_up_to=64))
    proof=dict(status='PASS',time=stamp(),backend=backend,real_training_representations=True,heldout_scores_evaluated=False,model_loaded=False,checks=checks,natural_sources=sources)
    atomic(ROOT/'provenance/SUBSPACE_REAL_ENGINEERING_SMOKE.json',proof);print(json.dumps(dict(status='PASS',checks=len(checks))),flush=True)

if __name__=='__main__':main()
