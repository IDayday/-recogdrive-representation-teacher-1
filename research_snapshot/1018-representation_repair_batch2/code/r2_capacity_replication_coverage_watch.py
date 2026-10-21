"""Mechanical milestones for predeclared capacity controls; no model choices."""
from r2_common import *


def main():
    folder=ROOT/'analysis/capacity_replication/coverage';protocol=read(ROOT/'config/CAPACITY_REPLICATION_PROTOCOL_V1.json')
    required={'warm_hard':6,'candidate_selector':4,'additional_joint_hard_continuous':6,'additional_joint_soft_joint':6}
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/pointer['path']);index={}
        for r in review['recipes']:
            if r['complete_five_folds']:index.setdefault((r['system'],r['method']),set()).add(r['policy'])
        flags={};ready=[]
        for variant in protocol['variants']:
            systems=[f"correction_{variant['id']}_K3_seed{i}" for i in range(3)]
            complete=[s for s in systems if all(len(index.get((s,m),set()))==n for m,n in required.items())]
            ready+=complete
            if systems[0] in complete:flags[variant['id']+'_fit0_complete22']=dict(systems=[systems[0]],recipes=22)
            if len(complete)==3:flags[variant['id']+'_all3fits_complete22']=dict(systems=systems,recipes=66)
        if len(ready)==9:flags['all198_complete']=dict(systems=ready,recipes=198)
        for name,details in flags.items():
            p=folder/(name+'.json')
            if not p.exists():atomic(p,dict(time=stamp(),status='COVERAGE_READY_FOR_AGENT_REVIEW',source=pointer,details=details,no_outcome_selection=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),complete_systems=ready,required_systems=9,required_methods=required,flags=sorted(flags)))
        time.sleep(120)


if __name__=='__main__':main()
