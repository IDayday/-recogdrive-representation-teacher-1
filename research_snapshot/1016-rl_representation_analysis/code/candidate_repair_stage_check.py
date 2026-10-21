"""Independent five-minute scientific audit; inspect saved outputs from every actual rank."""
from common import *
import numpy as np
from candidate_repair_fit import OUT

def main():
    setup('candidate_repair/stage_check');base=ROOT/'runs/candidate_repair_20261016_v1';done=set()
    while len(done)<2:
        failures=list((base/'failures').glob('*.json'))+list(base.glob('node*/FAILED.json'))
        assert not failures,str(failures)
        receipts=[(p,read(p)) for p in (base/'receipts').glob('coarse_s*.json')]
        for node in [0,1]:
            if node in done:continue
            selected=[(p,d) for p,d in receipts if d['rank']//16==node]
            if not selected or time.time()-min(p.stat().st_mtime for p,d in selected)<300:continue
            ranks=range(node*16,(node+1)*16);group={r:[] for r in ranks}
            for p,d in selected:group[d['rank']].append((p,d))
            if not all(group.values()):continue
            arms={a['id']:a for a in read(base/'stages/coarse/arms.json')};panel=read(base/'stages/coarse/panel.json');by={r['token']:r for r in panel}
            count=0;tokens=set();sites=set()
            for rank in ranks:
                for p,proof in sorted(group[rank],key=lambda pair:pair[0].stat().st_mtime)[-2:]:
                    result=base/'results'/p.name;assert sha(result)==proof['result_sha256'];doc=read(result)
                    per={}
                    for record in doc['records']:
                        count+=1;tokens.add(record['token']);a=arms.get(record['arm']);xyz=np.asarray(record['trajectory'])
                        assert xyz.shape==(8,3) and np.isfinite(xyz).all()
                        assert record['seed']==seed(record['token'],record['seed_index']) and record['quality']==quality(record['score']['score'])
                        assert all(np.isfinite(v) and 0<=v<=1+1e-8 for v in record['score'].values())
                        score=record['score'];assert abs(score['score']-score['no_at_fault_collisions']*score['drivable_area_compliance']*(5*score['ego_progress']+5*score['time_to_collision_within_bound']+2*score['comfort'])/12)<1e-8
                        if a:
                            assert record['edit']['sites']==1
                            assert record['edit']['relative_edit_l2_max']<=a['cap']+1e-6
                            sites.add((a['step'],a['layer'],a['token'],a['r']))
                        per.setdefault(record['token'],[]).append(record)
                    for token,records in per.items():
                        assert set(r['arm'] for r in records)=={'baseline'}|set(arms)
                        from repair_engine import baseline_row
                        original=baseline_row(by[token]);before=next(r for r in records if r['arm']=='baseline')
                        assert before['score']==original['score'] and np.array_equal(before['trajectory'],original['trajectory'])
                        assert all(r['feature_sha256']==original['feature_sha256'] and r['metric_sha256']==original['metric_sha256'] for r in records)
            atomic(OUT/f'FIVE_MINUTE_NODE{node}.json',dict(status='PASS',time=stamp(),node=node,ranks=16,records=count,tokens=len(tokens),sites=sorted(sites),
                original_native_replay_exact=True,all_arms_coverage=True,all_budgets_verified=True,all_seeds_inputs_scores_verified=True))
            print(json.dumps(dict(event='FIVE_MINUTE_PASS',node=node,ranks=16,records=count)),flush=True);done.add(node)
        if len(done)<2:time.sleep(30)

if __name__=='__main__':main()
