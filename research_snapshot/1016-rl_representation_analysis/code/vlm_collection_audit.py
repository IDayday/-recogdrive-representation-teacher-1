"""Real saved outputs from every rank, input-derived masks and native cached end states."""
from common import *
from vlm_core import VOUT
import numpy as np
from worker import load_features

def main():
    setup('vlm_repair/collection_audit');compatibility()
    base=ROOT/'runs/vlm_all_layers_20261016_v1';panel=read(base/'panel.json');by={r['token']:r for r in panel};cfg=read(ROOT/'configs/repair_final_baseline.json')
    grouped={r:[] for r in range(32)}
    for p in (base/'receipts').glob('*.json'):grouped[read(p)['rank']].append(p)
    assert all(grouped.values());records=0;maximum=0.;shapes=read(VOUT/'ENGINEERING_SMOKE_v2.json')['checks'][0]['block_shapes']
    for rank,paths in grouped.items():
        p=max(paths,key=lambda p:p.stat().st_mtime_ns);proof=read(p);result=base/'results'/p.name;assert sha(result)==proof['result_sha256'];doc=read(result)
        source=ROOT/doc['array_path'];assert sha(source)==doc['array_sha256']
        with np.load(source,allow_pickle=False) as data:
            assert data['global_indices'].tolist()==[r['global_index'] for r in doc['records']]
            for name,shape in shapes.items():
                x=np.asarray(data[name]);assert list(x.shape[1:])==shape and x.dtype==np.float32
                assert (np.isfinite(x).all(-1)|np.isnan(x).all(-1)).all()
            row=by[doc['records'][0]['token']];features,_,_=load_features(row,cfg)
            expected=features['last_hidden_state'].numpy().mean(0,dtype=np.float64);actual=data['language_norm'][0,0]
            maximum=max(maximum,float(np.max(np.abs(actual-expected))))
            assert np.allclose(actual,expected,atol=2e-4,rtol=1e-4)
        records+=len(doc['records'])
    output=VOUT/'COLLECTION_STAGE_AUDIT.json';assert not output.exists()
    record=dict(status='PASS',time=stamp(),ranks=32,cases=records,blocks=len(shapes),all_chunk_sha_verified=True,
        all_shapes_dtypes_missing_masks_verified=True,native_cached_final_mean_max_difference=maximum,
        note='Pooled mean reduction tolerances only; all 32 actual-rank smokes separately require exact hidden states, trajectories and scores')
    atomic(output,record);print(json.dumps(record),flush=True)

if __name__=='__main__':main()
