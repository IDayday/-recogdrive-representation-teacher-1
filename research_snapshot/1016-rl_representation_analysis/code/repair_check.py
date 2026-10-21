"""Real single-GPU full-method smoke and original independent scoring checks."""
from common import *
import numpy as np

def main():
    setup('repair/engineering');compatibility()
    import torch
    from worker import load_model,load_features
    from repair_engine import Editor,trace,baseline_row
    from repair_score import score_group
    from score import score_one
    cfg=read(ROOT/'configs/baseline.json');agent,runtime=load_model(cfg);editor=Editor(agent.action_head)
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--extra-only',action='store_true');p.add_argument('--natural-only',action='store_true');args=p.parse_args()
    versions={k:p._version for k,p in agent.named_parameters()};arms=read(ROOT/'repair_v1/screen_arms.json');checks=[]
    if args.extra_only:
        arms=[a for a in arms if a['method']=='soft_clip']+read(ROOT/'runs/repair_20261016_v1/stages/reference_diagnostic/arms.json')
    if args.natural_only:arms=read(ROOT/'runs/repair_20261016_v1/stages/natural_learn_screen/arms.json')
    for row in read(ROOT/'repair_v1/anchors.json'):
        features,_,meta=load_features(row,cfg);b=baseline_row(row);records=[]
        editor.set_reference(row['token'])
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']));assert np.array_equal(chain['trajectory'],b['trajectory'])
            for a in arms:
                pred,m=editor.predict(chain,a)
                assert np.isfinite(pred).all() and m['relative_edit_max']<=a['cap']+1e-6
                if a['method'] in ['mean','mlp','quality'] and a['alpha']==.5:
                    full,_=editor.predict(chain,dict(a,from_start=True));assert np.array_equal(pred,full),a['id']
                if a['alpha']==.1:
                    identity,_=editor.predict(chain,dict(a,alpha=0.));assert np.array_equal(identity,chain['trajectory'])
                records.append(dict(arm=a['id'],trajectory=pred.tolist(),edit=m))
        task=dict(metric_cache=row['metric_cache'],metric_sha256=b['metric_sha256'],scoring=cfg['scoring'],records=records)
        scores=score_group(task)
        # Independently reload cache for every checked trajectory, plus reversed cached order.
        reverse=score_group(dict(task,records=list(reversed(records))))
        assert [r['score'] for r in scores]==[r['score'] for r in reversed(reverse)]
        for r in scores[::max(1,len(scores)//12)]:
            fresh=score_one(dict(task,token=row['token'],trajectory=r['trajectory']));assert fresh['score']==r['score']
        checks.append(dict(token=row['token'],arms=len(scores),independent_rescores=len(scores[::max(1,len(scores)//12)]),scores=scores))
        print(json.dumps(dict(stage='engineering',token=row['token'],arms=len(scores))),flush=True)
    assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    editor.close()
    output='NATURAL_ENGINEERING_PASS.json' if args.natural_only else 'EXTRA_ENGINEERING_PASS.json' if args.extra_only else 'ENGINEERING_PASS.json'
    atomic(ROOT/'repair_v1'/output,dict(status='PASS',time=stamp(),runtime=runtime,all_methods_tested=True,
        full_chain_and_cached_prefix_exact=True,identity_exact=True,parameter_versions_unchanged=True,scoring_order_independent=True,checks=checks))

if __name__=='__main__':main()
