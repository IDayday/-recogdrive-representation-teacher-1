"""Task-scoped real-model smoke before each newly appended method/gate/composition stage."""
from common import *
import argparse
import copy
import numpy as np
from candidate_repair_queue import Dispatch

def main(args):
    setup('candidate_repair/probe/'+args.name);compatibility()
    import torch
    from worker import load_model,load_features
    from repair_engine import trace,baseline_row,geometries
    from repair_score import score_group
    cfg=read(ROOT/'configs/baseline.json');agent,runtime=load_model(cfg);editor=Dispatch(agent.action_head)
    versions={k:p._version for k,p in agent.named_parameters()};arms=read(args.arms);checks=[]
    for row in read(ROOT/'repair_v1/anchors.json'):
        features,_,meta=load_features(row,cfg);before=baseline_row(row)
        with torch.no_grad():
            chain=trace(agent,features,seed(row['token']));assert np.array_equal(chain['trajectory'],before['trajectory'])
            output=[dict(arm='baseline',trajectory=chain['trajectory'].tolist())]
            for a in arms:
                pred,m=editor.predict(chain,a);again,_=editor.predict(chain,a);assert np.array_equal(pred,again)
                zero=copy.deepcopy(a)
                if a['method']=='legacy':zero['legacy_arm']['alpha']=0.
                elif a['method']=='trajectory_scale':zero['factor']=1.
                elif 'components' in a:
                    for component in zero['components']:component['alpha']=0.
                else:zero['alpha']=0.
                identity,_=editor.predict(chain,zero);assert np.array_equal(identity,chain['trajectory'])
                assert m['relative_edit_max']<=a['cap']+1e-6
                if 'relative_edit_l2_max' in m:assert m['relative_edit_l2_max']<=a['cap']+1e-6
                output.append(dict(arm=a['id'],trajectory=pred.tolist(),edit=m,geometry=geometries(pred,chain['trajectory'])))
        scores=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=before['metric_sha256'],scoring=cfg['scoring'],records=output))
        assert scores[0]['score']==before['score'];checks.append(dict(token=row['token'],records=scores))
    editor.close();assert versions=={k:p._version for k,p in agent.named_parameters()} and all(p.grad is None for p in agent.parameters())
    atomic(ROOT/'candidate_repair_v1/probes'/(args.name+'.json'),dict(status='PASS',time=stamp(),arms_sha256=sha(args.arms),arms=len(arms),records=checks,base_unchanged=True,runtime=runtime))
    print(json.dumps(dict(status='PROBE_PASS',name=args.name,arms=len(arms))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--arms',type=Path,required=True);main(p.parse_args())
