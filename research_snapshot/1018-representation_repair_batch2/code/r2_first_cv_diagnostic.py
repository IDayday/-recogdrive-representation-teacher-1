"""Complete-fivefold candidate potential, respecting each policy's exact K arms.

A cache may contain the union of safety/PDMS arms. Never call that union K or
use it as an opportunity-matched K+1 candidate set.
"""
from r2_common import *


def main():
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);quality=np.load(source['quality']);pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/pointer['path']);recipes=[x for x in review['recipes'] if x['complete_five_folds'] and x['system']=='correction_K2_seed0' and x['method']=='candidate_selector'];assert len(recipes)==4
    banks={}
    for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
        d=read(p)
        if d.get('system')=='correction_K2_seed0' and d.get('mode')=='heldout':assert d['heldout_fold'] not in banks;banks[d['heldout_fold']]=(p,d)
    assert set(banks)==set(range(5));allcases=set();population_total=0;totals={r['policy']:dict(pool=np.zeros(3),fixed=np.zeros(3),Base3=np.zeros(3),expert=np.zeros((2,3)),exclusive=np.zeros(2,int),repair90=np.zeros(3,int)) for r in recipes};counts=[];lineage=[]
    folds=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 if r['subset']=='exploration' else -2 for r in rows])
    for held,(p,d) in sorted(banks.items()):
        assert sha(ROOT/d['matrix'])==d['matrix_sha256'];point=read(ROOT/d['point'])
        with np.load(ROOT/d['matrix']) as z:ii=np.array(z['global_indices']);scores=np.array(z['scores']);seeds=np.array(z['seeds']);ids=list(z['arm_ids'])
        assert np.all(folds[ii]==held) and not (allcases&set(ii.tolist()));allcases.update(ii.tolist());assert seeds.tolist()==[0,1,2]
        classes=np.where(quality[ii]<.7,0,np.where(quality[ii]>.9,1,2));sample=np.bincount(classes,minlength=3);pop=np.array([np.sum((folds==held)&(quality<.7)),np.sum((folds==held)&(quality>.9)),np.sum((folds==held)&(quality>=.7)&(quality<=.9))]);w=pop[classes]/sample[classes];population_total+=int(pop.sum());base=scores[:,0,:,0];draw=base.max(1)[:,None];policies=[]
        for configuration in point['policies']:
            key=configuration['id'];policy=read(ROOT/configuration['policy']);assert sha(ROOT/configuration['policy'])==configuration['policy_sha256'];assert len(policy['parts'])==2 and {a['slot'] for a in policy['parts']}=={0,1}
            pick=[0]+[ids.index(a['id']) for a in policy['parts']];s=scores[:,pick][...,0];oracle=s.max(1);selected=s.argmax(1)[:,0];fixedscore=s[np.arange(len(ii)),selected,:];t=totals[key]
            t['pool']+=((oracle-base)*w[:,None]).sum(0)*100;t['fixed']+=((fixedscore-base)*w[:,None]).sum(0)*100;t['Base3']+=((draw-base)*w[:,None]).sum(0)*100;t['expert']+=((s[:,1:,:]-base[:,None,:])*w[:,None,None]).sum(0)*100
            for a in [1,2]:t['exclusive'][a-1]+=np.sum((base[:,0]<.7)&(s[:,a,0]>.9)&(s[:,3-a,0]<=.9))
            t['repair90']+=np.sum((base<.7)&(oracle>.9),axis=0);policies.append(dict(id=key,policy=configuration['policy'],sha256=configuration['policy_sha256'],exact_candidate_arm_ids=[ids[j] for j in pick]))
        counts.append(dict(fold=held,sampled_cases=len(ii),sampled_FHM=sample.tolist(),population_FHM=pop.tolist(),cache_union_nonzero_arms=len(ids)-1));lineage.append(dict(fold=held,bank=str(p.relative_to(ROOT)),bank_sha256=sha(p),policies=policies))
    assert population_total==85813
    potentials={}
    for key,t in totals.items():potentials[key]=dict(pool_oracle_standardized_gain_by_noise=(t['pool']/population_total).tolist(),S0_fixed_privileged_expert_standardized_gain_by_noise=(t['fixed']/population_total).tolist(),Base_three_draw_privileged_oracle_gain_relative_to_each_noise=(t['Base3']/population_total).tolist(),single_expert_standardized_gain_by_noise=(t['expert']/population_total).tolist(),exclusive_S0_failure_to_over90_by_expert=t['exclusive'].tolist(),failure_to_over90_by_noise_in_candidate_oracle=t['repair90'].tolist())
    result=dict(status='FIRST_COMPLETE_EXPERTIZATION_SYSTEM_REVIEW',time=stamp(),system='correction_K2_seed0',complete_folds=5,sessions=recipes[0]['sessions'],sampled_cases=len(allcases),natural_population=population_total,fold_counts=counts,recipe_review=pointer,deployable_recipes=recipes,potentials=potentials,banks=lineage,
        inference='Complete candidate selection methods for thisK2 correction family have not converted privileged candidate potential into stable positive held-session gain. One family/K/fit, not completed batch2 or all expertization.',
        caveat='Class-standardized enriched held panels. Each policy uses exactly its own two nonzero arms, not the cached union of safety/PDMS arms. Base3 comparison is privileged across three noises; it is opportunity-matched only against S0. S0-fixed expert is selected with trueS0 score. Not natural final confirmation.',validation_accessed=False,test_accessed=False)
    destination=ROOT/'analysis/expertization_first_fivefold_review/SUMMARY.json';assert not destination.exists();atomic(destination,result);print(json.dumps(dict(path=str(destination.relative_to(ROOT)),potentials=potentials),ensure_ascii=False))


if __name__=='__main__':main()
