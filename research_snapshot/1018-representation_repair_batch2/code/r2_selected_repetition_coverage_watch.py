"""Wake on explicitly admitted whole-fit completion, including spatial families.

Coverage only: no ranking, thresholds, resource action or scientific decisions.
"""
from r2_common import *
import re


def main():
    folder=ROOT/'analysis/selected_repetition_coverage_flags'
    while True:
        targets=set()
        for name in ['PROVISIONAL_RECIPE_FRONTIER_PROTOCOL_V1','SELECTED_MODEL_RECIPE_FRONTIER_PROTOCOL_V1']:
            targets.update(read(ROOT/'config'/(name+'.json'))['systems'])
        latest=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/latest['path']);complete=[v for v in review['recipes'] if v['complete_five_folds']];by_system={};triples={}
        for value in complete:
            by_system.setdefault(value['system'],[]).append(value)
            match=re.fullmatch(r'(.+_K[2-8])_seed([0-2])',value['system'])
            if match:triples.setdefault((match[1],value['method'],value['policy']),set()).add(int(match[2]))
        flags={}
        for system in sorted(targets):
            values=by_system.get(system,[])
            if values:flags[system+'_first_complete']=dict(system=system,complete_recipes=len(values),examples=[dict(method=v['method'],policy=v['policy']) for v in values[:8]])
        stems={re.sub(r'_seed[0-2]$','',s) for s in targets}
        for stem in sorted(stems):
            matched=[dict(method=method,policy=policy) for (s,method,policy),seeds in triples.items() if s==stem and seeds=={0,1,2}]
            if matched:flags[stem+'_first_threefit_matched']=dict(system_stem=stem,matched_complete_recipes=matched)
        for name,details in flags.items():
            path=folder/(name+'.json')
            if not path.exists():atomic(path,dict(status='COVERAGE_READY_FOR_AGENT_REVIEW',time=stamp(),review=latest,details=details,no_outcome_or_significance_used=True,no_selection_or_resource_action=True))
        atomic(folder/'LIVE.json',dict(time=stamp(),targets=sorted(targets),complete_recipe_counts={s:len(by_system.get(s,[])) for s in targets},flags=sorted(flags)));time.sleep(120)


if __name__=='__main__':main()
