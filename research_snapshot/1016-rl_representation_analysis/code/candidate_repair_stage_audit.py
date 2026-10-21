"""Sample actual saved outputs from every active rank after a new stage begins."""
from common import *
import argparse
import numpy as np
from candidate_repair_fit import OUT
from repair_engine import baseline_row

def main(args):
    setup('candidate_repair/stage_audit/'+args.stage);base=ROOT/'runs/candidate_repair_20261016_v1';directory=base/'stages'/args.stage
    protocol=read(directory/'PROTOCOL.json');assert sha(directory/'arms.json')==protocol['arms_sha256'] and sha(directory/'panel.json')==protocol['panel_sha256']
    arms={a['id']:a for a in read(directory/'arms.json')};by={r['token']:r for r in read(directory/'panel.json')};groups={r:[] for r in range(32)}
    for p in (base/'receipts').glob(args.stage+'_s*.json'):
        proof=read(p);groups[proof['rank']].append((p,proof))
    assert all(groups.values()),'Wait for at least one completed chunk from every rank'
    count=0;tokens=set();seeds=set();saturated=0;maximum=0.
    for rank,items in groups.items():
        for p,proof in sorted(items,key=lambda row:row[0].stat().st_mtime)[-2:]:
            result=base/'results'/p.name;assert sha(result)==proof['result_sha256'];doc=read(result);per={}
            for r in doc['records']:
                count+=1;tokens.add(r['token']);seeds.add(r['seed_index']);row=by[r['token']];pose=np.asarray(r['trajectory'])
                assert pose.shape==(8,3) and np.isfinite(pose).all()
                assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(r['score']['score'])
                s=r['score'];assert all(np.isfinite(v) and 0<=v<=1+1e-8 for v in s.values())
                assert abs(s['score']-s['no_at_fault_collisions']*s['drivable_area_compliance']*(5*s['ego_progress']+5*s['time_to_collision_within_bound']+2*s['comfort'])/12)<1e-8
                if r['arm']!='baseline':
                    a=arms[r['arm']];edit=r['edit'];assert edit['relative_edit_max']<=a['cap']+1e-6
                    if a['method'] not in ['legacy','trajectory_scale']:
                        assert edit['relative_edit_l2_max']<=a['cap']+1e-6
                        assert edit['sites']==len(a.get('components',[a]));maximum=max(maximum,edit['relative_edit_l2_max'])
                        parts=a.get('components',[a])
                        if all(c.get('calibration')=='s' and c['gate']=='none' for c in parts):
                            assert abs(edit['relative_edit_l2_max']-a['cap'])<1e-6;saturated+=1
                if row.get('cohort')=='navtest':assert r['feature_sha256']==row['feature_sha256'] and r['metric_sha256']==row['metric_sha256']
                else:
                    original=baseline_row(row);assert r['feature_sha256']==original['feature_sha256'] and r['metric_sha256']==original['metric_sha256']
                per.setdefault((r['token'],r['seed_index']),[]).append(r)
            for (token,j),records in per.items():
                assert len(records)==len(arms)+1 and {r['arm'] for r in records}=={'baseline'}|set(arms)
                if j==0 and by[token].get('cohort')!='navtest':
                    b=next(r for r in records if r['arm']=='baseline');original=baseline_row(by[token]);assert b['score']==original['score'] and np.array_equal(b['trajectory'],original['trajectory'])
    output=OUT/'stage_audits'/(args.stage+'.json');assert not output.exists()
    record=dict(status='PASS',time=stamp(),stage=args.stage,ranks=32,records=count,scenes=len(tokens),seed_indices=sorted(seeds),
        protocol_sha256=sha(directory/'PROTOCOL.json'),inputs_seeds_shapes_scores_verified=True,all_arms_per_case=True,
        budgets_verified=True,normalized_saturated_records=saturated,relative_l2_max=maximum,native_s0_exact=True)
    atomic(output,record);print(json.dumps(record),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
