"""Mechanical predefined variant-wave coverage; no gain-based decisions."""
from r2_common import *


def main():
    setup('variant_wave_coverage_watch')
    folder=ROOT/'analysis/variant_wave_coverage_flags'
    families=['representation','response','correction'];suffixes=['causal','em1','unified_bcs']
    required={'warm_hard':6,'candidate_selector':4,'additional_joint_hard_continuous':6,'additional_joint_soft_joint':6}
    while True:
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/pointer['path']);full=[r for r in review['recipes'] if r['complete_five_folds']];index={}
        for r in full:index.setdefault((r['system'],r['method']),set()).add(r['policy'])
        flags={};initial=[]
        for suffix in suffixes:
            own=[]
            for family in families:
                for K in [2,3,4]:
                    system=f'{family}_{suffix}_K{K}_seed0';ready=all(len(index.get((system,m),set()))==n for m,n in required.items())
                    if ready:own.append(system);initial.append(system)
            if own:flags['first_complete22_'+suffix]=dict(examples=own[:3],methods=required)
        for K in [2,3,4]:
            expected=[f'{family}_{suffix}_K{K}_seed0' for family in families for suffix in suffixes]
            if all(s in initial for s in expected):flags['initial_all_banks_K'+str(K)+'_complete22']=dict(systems=expected,recipes=198)
        if len(initial)==27:flags['initial_variant_wave_all27_complete22']=dict(systems=initial,recipes=594)
        fixed_counts={}
        for suffix in ['causal','em1','spatial','unified_bc','unified_bcs']:
            expected=[f'{family}_{suffix}_K{K}_seed0' for family in families for K in range(2,9)]
            ready=[s for s in expected if len(index.get((s,'warm_hard'),set()))==6 and len(index.get((s,'candidate_selector'),set()))==4]
            fixed_counts[suffix]=len(ready)
            if len(ready)==21:flags['fixed_all_denseK_'+suffix]=dict(systems=ready,recipes=210)
        if all(v==21 for v in fixed_counts.values()):flags['fixed_all5banks_denseK_complete']=dict(systems=105,recipes=1050)
        primary=[f'{family}_K{K}_seed0' for family in families for K in range(2,9)]
        primary_ready=[s for s in primary if all(len(index.get((s,m),set()))==6 for m in ['joint_hard_continuous','joint_soft_joint'])]
        if len(primary_ready)==21:flags['primary_denseK_joint_complete']=dict(systems=primary_ready,recipes=252)
        for name,details in flags.items():
            path=folder/(name+'.json')
            if not path.exists():atomic(path,dict(time=stamp(),status='COVERAGE_READY_FOR_AGENT_REVIEW',review=pointer,details=details,not_outcome_based=True,no_selection_or_resource_action=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),initial_complete22_systems=len(initial),initial_required_systems=27,fixed_complete10_systems_by_bank=fixed_counts,primary_joint_complete12_systems=len(primary_ready),primary_required_systems=21,flags=sorted(flags)))
        time.sleep(120)


if __name__=='__main__':main()
