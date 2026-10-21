"""Real DSW check for selected risk/benefit gates before adding full validation jobs."""
from common import *
import argparse
import numpy as np

def main(args):
    setup('repair/gate_smoke');compatibility()
    import torch
    from worker import load_model,load_features
    from repair_engine import Editor,trace,baseline_row,geometries
    from repair_score import score_group
    from score import score_one
    cfg=read(ROOT/'configs/baseline.json');agent,runtime=load_model(cfg);editor=Editor(agent.action_head)
    arms=read(ROOT/args.arms);versions={k:p._version for k,p in agent.named_parameters()};proof=[]
    for row in read(ROOT/'repair_v1/anchors.json'):
        features,_,meta=load_features(row,cfg);b=baseline_row(row);records=[]
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']));assert np.array_equal(chain['trajectory'],b['trajectory'])
            for a in arms:
                pred,e=editor.predict(chain,a);again,_=editor.predict(chain,a);assert np.array_equal(pred,again)
                full,_=editor.predict(chain,dict(a,from_start=True));assert np.array_equal(pred,full)
                zero,_=editor.predict(chain,dict(a,alpha=0.));assert np.array_equal(zero,chain['trajectory'])
                assert np.isfinite(pred).all() and e['relative_edit_max']<=a['cap']+1e-6
                records.append(dict(arm=a['id'],trajectory=pred.tolist(),edit=e,geometry=geometries(pred,chain['trajectory'])))
        task=dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=records)
        scored=score_group(task)
        for r in scored[::max(1,len(scored)//8)]:
            independent=score_one(dict(task,token=row['token'],trajectory=r['trajectory']));assert independent['score']==r['score']
        proof.append(dict(token=row['token'],records=scored))
        print(json.dumps(dict(status='SMOKE',token=row['token'],arms=len(arms))),flush=True)
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    atomic(ROOT/args.output,dict(status='PASS',time=stamp(),runtime=runtime,arms_sha256=sha(ROOT/args.arms),
        identity_exact=True,full_and_cached_chain_exact=True,all_candidates_repeated_exact=True,base_unchanged=True,records=proof))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arms',required=True);p.add_argument('--output',required=True);main(p.parse_args())
