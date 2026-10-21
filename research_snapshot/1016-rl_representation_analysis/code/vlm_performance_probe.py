"""Engineering-only segmented timing and exact prefetch/batched-transfer equivalence."""
from common import *
import numpy as np
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT,raw_features
from vlm_intervene import Engine
from vlm_scan import save_npz
from vlm_repair_queue import stage,Fits,run_task
from repair_queue_v2 import init_score_unique,atomic_unique as atomic

def timed_score(task):
    from repair_score import score_group
    began=time.monotonic();result=score_group(task);return result,time.monotonic()-began

def main():
    setup('vlm_repair/performance');compatibility()
    import torch
    from repair_engine import baseline_row
    e=Engine();rows=read(ROOT/'repair_v1/anchors.json')[:2];fits=Fits();arms=[];base=VOUT/'performance_panel';base.mkdir(exist_ok=True)
    blocks=['vision_12','bridge_1','language_12','language_norm','interface_post']
    with torch.no_grad():e.forward_native(raw_features(rows[0]))
    for block in blocks:
        d=e.prefix[block].shape[-1];r=8;rng=np.random.default_rng(123);b=np.linalg.qr(rng.standard_normal((d,r)))[0];h=np.linalg.qr(rng.standard_normal((d,r)))[0]
        path=VOUT/'performance_fits'/(block+'.npz');arrays=dict(basis=b,haar=h,center=np.zeros(d),mh=np.ones(r),mf=np.zeros(r),risk_center=np.zeros(d),risk_direction=b[:,0],benefit_center=np.zeros(r),benefit_scale=np.ones(r),benefit_weights=np.zeros(r),benefit_intercept=np.array(1.))
        digest_value=save_npz(path,**{k:v.astype('float32') for k,v in arrays.items()})
        for method in ['mean','contract']:
            a=dict(block=block,group='patch_mean' if block.startswith(('vision','bridge')) else 'last8',fit_path=str(path.relative_to(ROOT)),fit_sha256=digest_value,method=method,alpha=.5,cap=.01,gate='none');a['id']='profile_'+digest(a)[:16];arms.append(a)
    gated=dict(arms[0],gate='benefit');gated['id']='profile_benefit';arms.append(gated)
    combo=dict(method='combination',parts=[dict(arms[0],alpha=0.),dict(arms[-3],alpha=0.)],id='profile_combo_identity',cap=.01);arms.append(combo)
    stage(base,'engineering',rows,arms,[0,1],chunk=2,arm_chunk=64);task=read(base/'tasks.json')[0]
    timings=[];outputs=[]
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        for prefetch in [False,True,False,True]:
            started=time.monotonic();records,timing=run_task(e,fits,task,base,pool,prefetch=prefetch);elapsed=time.monotonic()-started
            if outputs:assert records==outputs[0]
            else:outputs.append(records)
            # A zero-budget two-site combination is an exact native identity.
            by={(r['token'],r['seed_index'],r['arm']):r for r in records}
            for row in rows:
                for j in [0,1]:
                    assert by[(row['token'],j,'profile_combo_identity')]['trajectory']==by[(row['token'],j,'baseline')]['trajectory']
                    assert by[(row['token'],j,'profile_benefit')]['trajectory']==by[(row['token'],j,arms[0]['id'])]['trajectory']
            timings.append(dict(prefetch=prefetch,seconds=elapsed,stages=timing));print(json.dumps(timings[-1]),flush=True)
        # True disjoint short-stage timings deliberately synchronize in the probe only.
        disjoint=[]
        with torch.no_grad():
            for row in rows:
                start=time.monotonic();raw=raw_features(row);read_seconds=time.monotonic()-start
                torch.cuda.synchronize();start=time.monotonic();hidden=e.forward_native(raw);torch.cuda.synchronize();vlm_seconds=time.monotonic()-start
                trajectories=[];start=time.monotonic()
                for j in [0,1]:trajectories.append(e.trajectory(raw,hidden,seed(row['token'],j)))
                torch.cuda.synchronize();head_seconds=time.monotonic()-start
                start=time.monotonic();copied=torch.stack(trajectories).cpu().numpy();return_seconds=time.monotonic()-start
                before=baseline_row(row);req=dict(metric_cache=row['metric_cache'],metric_sha256=before['metric_sha256'],scoring=e.cfg['scoring'],records=[dict(arm=str(j),trajectory=p.tolist()) for j,p in enumerate(copied)])
                scored,score_seconds=pool.submit(timed_score,req).result(timeout=300)
                assert scored[0]['score']==before['score'];start=time.monotonic();atomic(base/(row['token']+'_timed.json'),scored);write_seconds=time.monotonic()-start
                disjoint.append(dict(token=row['token'],read_and_decode=read_seconds,native_vlm=vlm_seconds,head_two_seeds=head_seconds,device_return=return_seconds,scoring=score_seconds,write=write_seconds))
    proof=dict(status='PASS',time=stamp(),engineering_only=True,not_candidate_evaluation=True,records_exact_for_prefetch=True,benefit_gate_equivalence=True,zero_combination_exact=True,
        measurements=timings,disjoint_segments=disjoint,score_workers=3,adopt='single-thread input prefetch and batched device return; no score-process increase',
        limitation='two real anchors and synthetic edit directions measure engineering equivalence and local timing only, not population throughput; formal scene/task throughput still monitored',code_sha256=sha(ROOT/'code/vlm_intervene.py'))
    atomic(VOUT/'PERFORMANCE_PROBE.json',proof)
if __name__=='__main__':main()
