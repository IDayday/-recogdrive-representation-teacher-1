"""Coverage-only completion of the last bounded retained spatial regions."""
from r2_common import *


def main():
    stems=read(ROOT/'config/SELECTED_SPATIAL_FINAL_FRONTIER_PROTOCOL_V1.json')['systems_stems']
    methods={'warm_hard':6,'candidate_selector':4,
             'additional_joint_hard_continuous':6,'additional_joint_soft_joint':6}
    folder=ROOT/'analysis/selected_spatial_final_replication'
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json')
        index={}
        for row in read(ROOT/pointer['path'])['recipes']:
            if row['complete_five_folds']:
                index.setdefault((row['system'],row['method']),set()).add(row['policy'])
        counts={}
        for stem in stems:
            systems=[f'{stem}_seed{i}' for i in range(3)]
            counts[stem]=[s for s in systems if all(len(index.get((s,m),set()))==n for m,n in methods.items())]
            path=folder/(stem+'_THREE_FITS_READY.json')
            if len(counts[stem])==3 and not path.exists():
                atomic(path,dict(time=stamp(),status='COMPLETE22_THREE_FITS_READY',
                    snapshot=pointer,systems=systems,complete_fivefold_recipes=66,
                    no_outcome_based_filter=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),complete22_systems=counts))
        if all(len(v)==3 for v in counts.values()):return
        time.sleep(120)


if __name__=='__main__':
    main()
