"""Describe matched complete five-fold recipes across independent whole fits.

The fit mean is a summary, never a deployable mixture or additional sample size.
No new significance calculation, selection lock or validation/test access.
"""
from r2_common import *
import re


def main():
    from collections import defaultdict
    import numpy as np
    latest=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');assert sha(ROOT/latest['path'])==latest['sha256'];review=read(ROOT/latest['path']);groups=defaultdict(dict)
    for v in review['recipes']:
        if not v['complete_five_folds']:continue
        match=re.fullmatch(r'(.+_K[2-8])_seed([0-2])',v['system'])
        if match:
            key=(match[1],v['method'],v['policy']);fit=int(match[2]);assert fit not in groups[key];groups[key][fit]=v
    records=[]
    for (stem,method,policy),fits in sorted(groups.items()):
        if len(fits)<2:continue
        ids=sorted(fits);noise=np.array([fits[s]['standardized_pdms_gain_by_noise'] for s in ids]);gain=noise.mean(1);complete=ids==[0,1,2]
        records.append(dict(system_stem=stem,method=method,policy=policy,fit_indices=ids,all_three_fits_complete=complete,
            complete_fivefold_for_every_included_fit=True,fit_gain_by_noise=noise.tolist(),fit_mean_gains=gain.tolist(),fit_mean_standardized_gain=float(gain.mean()),fit_mean_gain_by_noise=noise.mean(0).tolist(),
            smallest_fit_mean=float(gain.min()),largest_fit_mean=float(gain.max()),every_included_fit_mean_positive=bool(np.all(gain>0)),every_included_fit_every_noise_positive=bool(np.all(noise>0)),every_included_fit_approx_safety=all(fits[s]['approximate_safety_all_noise'] for s in ids),
            descriptive_threefit_positive_and_approx_safe=bool(complete and np.all(noise>0) and all(fits[s]['approximate_safety_all_noise'] for s in ids)),source_recipes=[fits[s] for s in ids]))
    folder=ROOT/'analysis/repetition_cv_reviews'/Path(latest['path']).parent.name;folder.mkdir(parents=True,exist_ok=True);path=folder/'SUMMARY.json';assert not path.exists()
    complete=[v for v in records if v['all_three_fits_complete']];summary=dict(time=stamp(),status='EXPLORATORY_WHOLE_FIT_REPETITION_DESCRIPTION',snapshot=latest,recipes=records,matched_two_or_three_fit_recipes=len(records),matched_three_fit_recipes=len(complete),threefit_all_noise_positive_and_approx_safe=sum(v['descriptive_threefit_positive_and_approx_safe'] for v in complete),scope='Same held scenes and paired noise across fits. Mean across fits is not a new routed model or ensemble, not extra independent cases, and not a significance or deployment claim.',validation_accessed=False,test_accessed=False)
    atomic(path,summary);atomic(ROOT/'analysis/repetition_cv_reviews/LATEST.json',dict(time=stamp(),path=str(path.relative_to(ROOT)),sha256=sha(path)));print(json.dumps(dict(path=str(path.relative_to(ROOT)),two_or_three_fit=len(records),complete_threefit=len(complete),descriptive_all_positive_safe=summary['threefit_all_noise_positive_and_approx_safe'])))


if __name__=='__main__':main()
