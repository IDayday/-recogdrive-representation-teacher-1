"""Mechanical primary-family/K/joint coverage flags; never choose by scores."""
from r2_common import *
import re


def main():
    folder=ROOT/'analysis/primary_cv_coverage_flags'
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');report=read(ROOT/pointer['path']);full=[r for r in report['recipes'] if r['complete_five_folds']];core=[]
        for r in full:
            m=re.fullmatch(r'(representation|response|correction)_K([2-8])_seed([0-2])',r['system'])
            if m:core.append((r,m[1],int(m[2]),int(m[3])))
        flags={}
        for family in ['representation','response','correction']:
            own=[r for r,f,k,s in core if f==family and s==0]
            if own:flags['first_complete_'+family]=dict(examples=[dict(method=r['method'],system=r['system'],policy=r['policy']) for r in own[:4]])
        if len({f for r,f,k,s in core if s==0})==3:flags['all_three_primary_families_present']=dict(families=['representation','response','correction'])
        for K in [2,3,4,5,6,7,8]:
            systems={r['system'] for r,f,k,s in core if s==0 and k==K and r['method'] in ['candidate_selector','warm_hard']}
            if len(systems)==3:flags['all_three_primary_K'+str(K)]=dict(systems=sorted(systems))
        joints=[r for r in full if 'joint' in r['method']]
        if joints:flags['first_complete_true_joint']=dict(examples=[dict(method=r['method'],system=r['system'],policy=r['policy']) for r in joints[:4]])
        for seed in [1,2]:
            own=[r for r,f,k,s in core if s==seed]
            if own:flags['first_complete_independent_expert_fit'+str(seed)]=dict(examples=[dict(method=r['method'],system=r['system'],policy=r['policy']) for r in own[:4]])
        for name,details in flags.items():
            path=folder/(name+'.json')
            if not path.exists():atomic(path,dict(status='COVERAGE_READY_FOR_AGENT_REVIEW',time=stamp(),flag=name,review=pointer,details=details,not_outcome_or_effect_based=True,no_selection_or_resource_action=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),full_recipes=len(full),core_recipes=len(core),flags=sorted(flags)));time.sleep(120)


if __name__=='__main__':main()
