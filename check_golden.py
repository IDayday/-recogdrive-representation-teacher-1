"""Compare a local replay against nine saved first-batch trajectories and scores."""
from pathlib import Path
import argparse,json
import numpy as np
ROOT=Path(__file__).resolve().parent
def main(a):
    g=json.loads((ROOT/'reference/golden.json').read_text());protocols=[json.loads(p.read_text()) for p in a.input.glob('protocol_rank*.json')];p=protocols[0];ids=['baseline']+p['methods'];checked=[]
    for r in g['records']:
        folder=a.input/'cases'/r['token']
        if not (folder/'COMPLETE.json').exists():raise AssertionError(('Missing scene',r['token']))
        with np.load(folder/'branches.npz') as z:
            i=p['seeds'].index(r['seed_index']);k=ids.index(r['arm']);actual=z['trajectories'][i,k];expected=np.array(r['trajectory'],dtype=np.float32)
            error=float(np.max(np.abs(actual-expected)));exact=bool(np.array_equal(actual,expected));score=np.array([r['score'][f] for f in ['score','no_at_fault_collisions','drivable_area_compliance','ego_progress','time_to_collision_within_bound','comfort','driving_direction_compliance']]);score_error=float(np.max(np.abs(z['scores'][i,k]-score)))
        if error>a.trajectory_atol or score_error>a.score_atol:raise AssertionError((r['token'],r['arm'],error,score_error))
        checked.append(dict(token=r['token'],method=r['arm'],trajectory_bitwise_equal=exact,trajectory_max_abs_error=error,score_max_abs_error=score_error))
    result=dict(status='PASS',records=checked,trajectory_atol=a.trajectory_atol,score_atol=a.score_atol);print(json.dumps(result,ensure_ascii=False,indent=2));(a.input/'GOLDEN_ACCEPTANCE.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--trajectory-atol',type=float,default=0);p.add_argument('--score-atol',type=float,default=0);main(p.parse_args())
