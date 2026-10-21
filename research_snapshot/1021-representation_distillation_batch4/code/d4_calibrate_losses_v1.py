"""Training-only scale calibration at the unified interface, without GT."""
from d4_common import *
import traceback


def main():
    setup('loss_calibration_v1');compatibility()
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from r3_runtime import prediction
    from vlm_core import raw_features
    from d4_student_v1 import losses
    source=read(ROOT/'manifests/R2_SCENES_V1.json')
    hard=[s['global_index'] for s in source if s['subset']=='exploration' and s['pool']=='I' and s['Base_any_below70']]
    other=[s['global_index'] for s in source if s['subset']=='exploration' and s['pool']=='I' and not s['Base_any_below70']]
    rng=np.random.default_rng(2026102103)
    indices=np.concatenate([rng.choice(hard,size=8,replace=False),rng.choice(other,size=24,replace=False)]).tolist()
    atomic(ROOT/'manifests/LOSS_CALIBRATION_INDICES_V1.json',indices)
    config=dict(indices=indices,selection='Eight hard I and 24 other I, train only, no validation/test',seed=2026102103)
    engine=Engine();measurements=[]
    missing=[i for i in indices if not (ROOT/'runs/full_context_replay_v1/cases'/source[i]['token']/'RESULT.json').exists()]
    if missing:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor
        from r3_runtime import init_scorer
        from d4_replay_teacher_v1 import run as replay
        path=ROOT/'manifests/R2_SCENES_V1.json';pack=B3/'teachers/first42_v1/PACK.json'
        task=dict(id='loss_calibration_local_replay_v1',output_stage='runs/loss_calibration_replay_v1',indices=missing,
            scenes=str(path),scenes_sha256=sha(path),pack=str(pack),pack_sha256=sha(pack))
        with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:replay(engine,task,pool)
    for index in indices:
        row=source[index];features=raw_features(row)
        record_path=ROOT/'runs/full_context_replay_v1/cases'/row['token']/'RESULT.json'
        if not record_path.exists():record_path=ROOT/'runs/loss_calibration_replay_v1/cases'/row['token']/'RESULT.json'
        record=read(record_path)
        with np.load(ROOT/record['arrays']['path'],allow_pickle=False) as z:target={k:np.array(z[k]) for k in z.files}
        hidden=engine.forward_native(features);h=engine.prefix['interface_post'].detach().clone().requires_grad_(True)
        trajectory,_=prediction(engine,features,hidden,0,row['token'],interface=h,gradient=True,capture=False)
        outputs=dict(interface=h,prediction=trajectory.unsqueeze(0));lh,lt=losses(outputs,target,0)
        gh=torch.autograd.grad(lh,h,retain_graph=True)[0];gt=torch.autograd.grad(lt,h)[0]
        values=[float(lh.detach()),float(lt.detach()),float(gh.norm()),float(gt.norm())]
        assert np.isfinite(values).all()
        measurements.append(dict(index=index,token=row['token'],H=values[0],T=values[1],H_interface_gradient_norm=values[2],T_interface_gradient_norm=values[3]))
        assert all(p.grad is None for p in engine.agent.parameters())
    h=np.asarray([m['H_interface_gradient_norm'] for m in measurements]);t=np.asarray([m['T_interface_gradient_norm'] for m in measurements]);valid=(h>0)&(t>0)
    assert valid.sum()>=16
    weight=float(np.median(h[valid])/np.median(t[valid]));assert np.isfinite(weight) and weight>0
    proof=dict(status='FROZEN_TRAIN_ONLY_INTERFACE_GRADIENT_SCALE',time=stamp(),configuration=config,measurements=measurements,
        lambda_H=1.,lambda_T=weight,rule='Ratio of median nonzero H and T interface gradient norms, same valid pairs',
        valid_pairs=int(valid.sum()),zero_gradient_pairs=int((~valid).sum()),nominal_interface_gradient_ratio=1.,
        GT_used=False,validation_or_test_used=False,source_sha256=sha(Path(__file__)))
    atomic(ROOT/'configs/LOSS_CALIBRATION_V1.json',proof);print(json.dumps({k:proof[k] for k in ['status','lambda_H','lambda_T','valid_pairs']}),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'provenance/LOSS_CALIBRATION_FAILED_V1.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
