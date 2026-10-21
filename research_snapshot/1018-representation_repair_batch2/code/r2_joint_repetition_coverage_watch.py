"""Mechanical joint-policy fitted-replica coverage, without score selection."""
from r2_common import *


def main():
    setup('joint_repetition_coverage_watch')
    folder=ROOT/'analysis/joint_repetition_coverage_flags'
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json')
        report=read(ROOT/pointer['path'])
        full=[r for r in report['recipes'] if r['complete_five_folds']]
        flags={}
        for kind in ['soft_joint','hard_continuous']:
            for fit in [1,2]:
                system='correction_K3_seed'+str(fit)
                own=[r for r in full if r['system']==system and r['method']=='joint_'+kind]
                if len(own)==6:
                    flags[kind+'_correction_K3_seed'+str(fit)]=dict(system=system,recipes=[r['policy'] for r in own])
            if all(kind+'_correction_K3_seed'+str(fit) in flags for fit in [1,2]):
                flags[kind+'_correction_K3_both_independent_fits']=dict(fits=[1,2],recipes_per_fit=6)
        for name,details in flags.items():
            path=folder/(name+'.json')
            if not path.exists():
                atomic(path,dict(status='COVERAGE_READY_FOR_AGENT_REVIEW',time=stamp(),review=pointer,details=details,
                    not_outcome_or_effect_based=True,no_selection_or_resource_action=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),review=pointer,flags=sorted(flags)))
        time.sleep(120)


if __name__=='__main__':main()
