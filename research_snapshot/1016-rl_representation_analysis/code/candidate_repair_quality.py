"""Continuous natural-PDMS gradients in frozen candidate bases; no runtime-code changes."""
from common import *
import numpy as np
from candidate_repair_fit import OUT
from candidate_repair_prepare import arm
from candidate_repair_followup import probe
from candidate_repair_queue import stage
from paired_observation import save_arrays

def main():
    setup('candidate_repair/quality');fits=read(OUT/'FITS_READY.json')['fits'];meta=read(ROOT/'analysis/subspace_scan_v2/natural_metadata.json')
    q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy');exp=np.array([r['subset']=='exploration' for r in meta]);y=q[exp]
    arms=[];proofs=[]
    for spec in fits:
        if spec['kind'] not in ['candidate','equal','full']:continue
        assert sha(ROOT/spec['coordinate_path'])==spec['coordinate_sha256']
        x=np.asarray(np.load(ROOT/spec['coordinate_path'],mmap_mode='r'),dtype=np.float64)
        mean=x.mean(0);scale=np.maximum(x.std(0),1e-6);z=(x-mean)/scale
        coef=np.linalg.solve(z.T@z+.1*len(z)*np.eye(z.shape[1]),z.T@(y-y.mean()));gradient=coef/scale
        with np.load(ROOT/spec['fit_path']) as source:arrays={k:source[k] for k in source.files}
        # Match native mean-gap norm so alpha/cap curves compare directions at equal pre-cap scale.
        gradient=gradient/max(np.linalg.norm(gradient),1e-12)*np.linalg.norm(arrays['n_mh']-arrays['n_ml'])
        arrays.update(q_mh=gradient,q_ml=np.zeros_like(gradient),q_scale=arrays['n_scale'],q_ridge=coef,q_input_mean=mean,q_input_scale=scale)
        ident=spec['id']+'__quality';p=OUT/'fits'/(ident+'.npz');assert not p.exists();save_arrays(p,**arrays)
        new=dict(spec,id=ident,fit_path=str(p.relative_to(ROOT)),fit_sha256=sha(p),time=stamp(),quality_gradient='ridge .1, all exploration natural continuous PDMS; norm matched native class mean gap')
        atomic(p.with_suffix('.json'),new);proofs.append(dict(id=ident,sha256=sha(p),candidate=spec['candidate']['id']))
        if spec['kind']=='candidate':
            for alpha in [.1,.5,1.]:
                for gate in ['none','risk99']:arms.append(arm(new,'mean',alpha,calibration='q',gate=gate,mechanism='quality_gradient'))
            for cap in [.01,.1]:arms.append(arm(new,'mean',.5,calibration='q',cap=cap,mechanism='quality_gradient'))
    atomic(OUT/'QUALITY_FITS_READY.json',dict(status='PASS',time=stamp(),fits=proofs,arms=arms,base_updated=False,fit_subset='exploration'))
    assert len(arms)==80 and len({a['id'] for a in arms})==80
    probe('quality_screen',arms)
    tasks=stage(ROOT/'runs/candidate_repair_20261016_v1','quality_screen',read(OUT/'coarse_panel.json'),arms,[0],chunk=4)
    print(json.dumps(dict(event='QUALITY_SCREEN_APPENDED',tasks=tasks,arms=len(arms))),flush=True)

if __name__=='__main__':main()
