"""Mechanical whole-fit coverage for the selected existing K6 recipe; no choices."""
from r2_common import *


def main():
    setup('selected_k6_coverage_watch_v1')
    folder=ROOT/'analysis/selected_representation_K6_replication'
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/pointer['path'])
        index={}
        for row in review['recipes']:
            if row['complete_five_folds']:
                index.setdefault((row['system'],row['method']),set()).add(row['policy'])
        systems=[f'representation_K6_seed{i}' for i in range(3)]
        joint=[s for s in systems if all(len(index.get((s,m),set()))==6 for m in ['joint_hard_continuous','joint_soft_joint'])]
        fixed=[s for s in systems if len(index.get((s,'warm_hard'),set()))==6 and len(index.get((s,'candidate_selector'),set()))==4]
        if len(joint)==3 and not (folder/'JOINT_THREE_FITS_READY.json').exists():
            atomic(folder/'JOINT_THREE_FITS_READY.json',dict(time=stamp(),status='READY_FOR_AGENT_REVIEW',snapshot=pointer,
                systems=systems,complete_fivefold_joint_recipes=36,no_outcome_based_filter=True))
        if len(joint)==len(fixed)==3 and not (folder/'ALL22_THREE_FITS_READY.json').exists():
            atomic(folder/'ALL22_THREE_FITS_READY.json',dict(time=stamp(),status='READY_FOR_AGENT_REVIEW',snapshot=pointer,
                systems=systems,complete_fivefold_recipes=66,no_outcome_based_filter=True))
            return
        atomic(folder/'LIVE.json',dict(time=stamp(),joint_complete_systems=joint,fixed_complete_systems=fixed,required=systems))
        time.sleep(120)


if __name__=='__main__':main()
