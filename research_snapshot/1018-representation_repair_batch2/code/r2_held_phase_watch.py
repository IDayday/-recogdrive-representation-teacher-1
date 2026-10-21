"""Mechanical whole-point held-session completion flags, no score decisions."""
from r2_common import *


def main():
    watched={};finished={};names=['warm_hard_cv_v1','candidate_selector_cv_v1','joint_policy_cv_v1']
    while True:
        for name in names:
            stage=ROOT/'runs'/name;points=watched.setdefault(name,{});done=finished.setdefault(name,set());receipts={p.stem for p in (stage/'receipts').glob('*.json')}
            for p in (stage/'points').glob('*.json'):
                if p.stem in points or p.stem in done:continue
                d=read(p)
                if d['mode']!='heldout':done.add(p.stem);continue
                points[p.stem]=dict(id=d['id'],point=str(p.relative_to(ROOT)),heldout_fold=d['heldout_fold'],system=d['system'],cases=len(d['panel']),chunks=[d['id']+'_%04d'%i for i in range(0,len(d['panel']),4)])
            for ident,point in list(points.items()):
                if all(c in receipts for c in point['chunks']):
                    flag=stage/'FIRST_HELD_COMPLETE.json'
                    if not flag.exists():atomic(flag,dict(status='FIRST_HELD_POINT_COMPLETE',time=stamp(),**point,scope='One genuine whole-system held-fold point, not completion of all folds/recipes.'))
                    points.pop(ident);done.add(ident)
        atomic(ROOT/'analysis/held_phase_watch/LIVE.json',dict(time=stamp(),pending_held_points={k:len(v) for k,v in watched.items()},finished_or_nonheld_points={k:len(v) for k,v in finished.items()}))
        time.sleep(60)


if __name__=='__main__':main()
