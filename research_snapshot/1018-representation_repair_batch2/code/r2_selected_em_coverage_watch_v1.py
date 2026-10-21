"""Completion-only notifications for two admitted EM families and all three fits."""
from r2_common import *


def main():
    folder=ROOT/'analysis/selected_em1_K3_replication'
    required={'warm_hard':6, 'candidate_selector':4,
              'additional_joint_hard_continuous':6, 'additional_joint_soft_joint':6}
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json')
        index={}
        for row in read(ROOT/pointer['path'])['recipes']:
            if row['complete_five_folds']:
                index.setdefault((row['system'],row['method']),set()).add(row['policy'])
        coverage={}
        for family in ['representation','response']:
            systems=[f'{family}_em1_K3_seed{i}' for i in range(3)]
            ready=[s for s in systems if all(len(index.get((s,m),set()))==n for m,n in required.items())]
            coverage[family]=ready
            path=folder/(family+'_THREE_FITS_READY.json')
            if len(ready)==3 and not path.exists():
                atomic(path,dict(time=stamp(),status='COVERAGE_READY_FOR_AGENT_REVIEW',
                    snapshot=pointer,systems=systems,complete_fivefold_recipes=66,
                    no_outcome_based_filter=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),complete22_systems=coverage))
        if all(len(s)==3 for s in coverage.values()):return
        time.sleep(120)


if __name__=='__main__':
    main()
