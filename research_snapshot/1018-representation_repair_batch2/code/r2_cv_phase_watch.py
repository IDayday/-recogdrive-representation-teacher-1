"""Mechanical whole-five-fold completion flags; no winner selection."""
from r2_common import *
from collections import Counter


def main():
    while True:
        latest=ROOT/'analysis/extended_cv_reviews/LATEST.json';counts={};complete=[]
        if latest.exists():
            meta=read(latest);review=read(ROOT/meta['path']);complete=[r for r in review['recipes'] if r['complete_five_folds']];counts=dict(Counter(r['method'] for r in complete))
            tests=[('first_complete_five_fold_recipe',len(complete)>=1)]
            tests += [('complete_recipes_at_least_'+str(n),len(complete)>=n) for n in [10,25,50,100,200,500,1000]]
            for method in ['candidate_selector','warm_hard']:
                present={(r['system'],r['policy']) for r in complete if r['method']==method}
                expected={(f'{family}_K{k}_seed0','PDMS_trajectory') for family in ['representation','response','correction'] for k in range(2,9)}
                tests.append((method+'_all_K_seed0_fivefold',expected<=present))
            for name,passed in tests:
                flag=ROOT/'analysis/cv_phase_flags'/(name+'.json')
                if passed and not flag.exists():atomic(flag,dict(status='PHASE_READY_FOR_AGENT_REVIEW',time=stamp(),flag=name,complete_recipes=len(complete),counts=counts,review=meta['path'],review_sha256=meta['sha256'],winner_selected=False,validation_accessed=False,test_accessed=False))
        atomic(ROOT/'analysis/cv_phase_flags/LIVE.json',dict(time=stamp(),complete_recipes=len(complete),counts=counts,mechanical_only=True))
        time.sleep(60)


if __name__=='__main__':main()
