"""All 580 arms on actual RL inputs, spawned scorers, and independent fresh-cache checks."""
from common import *
import numpy as np
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from candidate_repair_queue import Dispatch,init_score_unique,smoke
from candidate_repair_fit import OUT

def main():
    setup('candidate_repair/engineering');compatibility()
    import torch
    from worker import load_model,load_features
    from repair_engine import trace,baseline_row,geometries
    from repair_score import score_group
    from score import score_one
    cfg=read(ROOT/'configs/baseline.json');agent,runtime=load_model(cfg);editor=Dispatch(agent.action_head)
    versions={k:p._version for k,p in agent.named_parameters()};arms=read(OUT/'coarse_arms.json');checks=[]
    smoke(agent,editor,cfg,0,ROOT/'runs/candidate_repair_dsw_v4')
    arms=list({a['id']:a for a in arms+read(OUT/'smoke_arms.json')}.values())
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        for row in read(ROOT/'repair_v1/anchors.json'):
            features,_,meta=load_features(row,cfg);b=baseline_row(row)
            with torch.no_grad():
                chain=trace(agent,features,seed(row['token']));assert np.array_equal(chain['trajectory'],b['trajectory'])
                candidates=[dict(arm='baseline',trajectory=chain['trajectory'].tolist())]
                for arm in arms:
                    pred,edit=editor.predict(chain,arm)
                    assert edit['relative_edit_max']<=arm['cap']+1e-6 and edit['relative_edit_l2_max']<=arm['cap']+1e-6
                    candidates.append(dict(arm=arm['id'],trajectory=pred.tolist(),edit=edit,geometry=geometries(pred,chain['trajectory'])))
            task=dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=candidates)
            scored=pool.submit(score_group,task).result(timeout=1200);assert scored[0]['score']==b['score']
            for record in scored[::29]:
                actual=score_one(dict(task,token=row['token'],trajectory=record['trajectory']));assert actual['score']==record['score']
            checks.append(dict(token=row['token'],records=scored,feature_sha256=meta['feature_sha256'],independent_rescores=len(scored[::29])))
            print(json.dumps(dict(event='ALL_ARMS_ANCHOR_PASS',token=row['token'],arms=len(arms))),flush=True)
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters());editor.close()
    atomic(OUT/'ENGINEERING_PASS_v2.json',dict(status='PASS',time=stamp(),runtime=runtime,arms=len(arms),checks=checks,
        spawned_scoring=True,all_caps_verified=True,base_unchanged=True,code_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'code/candidate_repair_engine.py',ROOT/'code/candidate_repair_queue.py']}))

if __name__=='__main__':main()
