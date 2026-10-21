"""Coverage-checked upstream intervention results; repeated baseline chunks must be exact."""
from common import *
import argparse
import numpy as np
from collections import Counter
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def save_npy(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert np.array_equal(np.load(path,mmap_mode='r'),value,equal_nan=True);return sha(path)
    import uuid
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('wb') as stream:np.save(stream,value)
    tmp.replace(path);return sha(path)

def summarize(base,name):
    output=VOUT/'analysis'/name
    if (output/'SUMMARY.json').exists():return read(output/'SUMMARY.json')
    folder=base/'stages'/name;p=read(folder/'PROTOCOL.json');rows=read(folder/'panel.json');arms=read(folder/'arms.json');seeds=p['seeds']
    assert sha(folder/'arms.json')==p['arms_sha256'] and sha(folder/'panel.json')==p['panel_sha256']
    paths=list((base/'receipts').glob(name+'_a*.json'))
    if len(paths)!=p['tasks']:return None
    ids=['baseline']+[a['id'] for a in arms];ai={a:i for i,a in enumerate(ids)};ri={r['token']:i for i,r in enumerate(rows)};si={j:i for i,j in enumerate(seeds)};shape=(len(seeds),len(rows),len(ids))
    data=np.full(shape+(7,),np.nan);edits=np.full(shape+(5,),np.nan,dtype=np.float32);seen=np.zeros(shape,dtype=bool);duplicates=0;sources=[]
    for proof_path in sorted(paths):
        proof=read(proof_path);path=base/'results'/proof_path.name;assert sha(path)==proof['result_sha256'];result=read(path);assert result['task']['stage']==name
        for r in result['records']:
            j=si[r['seed_index']];i=ri[r['token']];a=ai[r['arm']];v=np.array([r['score'][f] for f in ['score']+COMPONENTS]);assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(v[0])
            if seen[j,i,a]:assert a==0 and np.array_equal(data[j,i,a],v);duplicates+=1;continue
            seen[j,i,a]=True;data[j,i,a]=v;e=r['edit'];g=r['geometry'];edits[j,i,a]=[e['relative_edit_max'],e['gate_mean'],g['trajectory_displacement_mean_m'],g['trajectory_displacement_max_m'],g['second_difference_change_max_m']]
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=proof['result_sha256']))
    assert seen.all() and np.isfinite(data).all() and np.isfinite(edits).all();base_scores=data[:,:,0,:];q=base_scores[:,:,0]
    enriched=not name.startswith(('validation','final_test','navtrain'))
    pop=Counter(r['quality'] for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration');sample=Counter(r.get('quality') for r in rows)
    weights=np.array([pop[r['quality']]/sample[r['quality']] for r in rows]) if enriched else np.ones(len(rows));weights=weights/weights.sum()
    summaries=[]
    for i,a in enumerate(arms,1):
        v=data[:,:,i,:];after=v[:,:,0];delta=after-q;failure=q<.7;high=q>.9;active=edits[:,:,i,0]>1e-8
        def mean(z):return float(np.mean(z@weights)*100)
        row=dict(arm=a,mean_delta_pdms=float(delta.mean()*100),population_weighted_delta_pdms=mean(delta),by_seed_delta_pdms=(delta.mean(1)*100).tolist(),
            oracle_failure_gate_delta_pdms=mean(delta*failure),oracle_benefit_gate_delta_pdms=mean(np.maximum(delta,0)),baseline_failures=int(failure.sum()),
            repaired_ge70=int((failure&(after>=.7)).sum()),repaired_gt90=int((failure&(after>.9)).sum()),high_to_failure=int((high&(after<.7)).sum()),high_to_le90=int((high&(after<=.9)).sum()),
            failure_delta_pdms=float(delta[failure].mean()*100) if failure.any() else None,high_delta_pdms=float(delta[high].mean()*100) if high.any() else None,
            failure_net=int((after<.7).sum()-failure.sum()),zero_net=int((after<=1e-10).sum()-(q<=1e-10).sum()),
            activation_rate=float(active.mean()),relative_edit_max=float(edits[:,:,i,0].max()),relative_edit_median=float(np.median(edits[:,:,i,0])),gate_mean=float(edits[:,:,i,1].mean()),
            displacement_mean_m=float(edits[:,:,i,2].mean()),displacement_max_m=float(edits[:,:,i,3].max()),session_count=len({r['session'] for r in rows}))
        for label,field in [('collision',1),('offroad',2),('ttc',4)]:
            bf=base_scores[:,:,field]<1-1e-7;af=v[:,:,field]<1-1e-7;row.update({label+'_net':int(af.sum()-bf.sum()),label+'_new':int((~bf&af).sum()),label+'_removed':int((bf&~af).sum())})
        row['safe_net']=all(row[k]<=0 for k in ['collision_net','offroad_net','zero_net']) and row['population_weighted_delta_pdms']>=0
        summaries.append(row)
    summaries.sort(key=lambda r:r['population_weighted_delta_pdms'],reverse=True)
    score_sha=save_npy(output/'scores.npy',data);edit_sha=save_npy(output/'edits.npy',edits);atomic(output/'arms.json',arms);atomic(output/'rows.json',rows)
    result=dict(status='COMPLETE',time=stamp(),stage=name,protocol=p,coverage_exact=True,repeated_baselines_verified=duplicates,distinct_records=int(np.prod(shape)),source_records=int(np.prod(shape))+duplicates,sources=sources,scores_sha256=score_sha,edits_sha256=edit_sha,
        enriched_development_panel=enriched,population_weighting='S0 class-stratum inverse selection probability on exploration panels; no weighting on full validation/test',summaries=summaries,
        baseline=dict(mean_pdms=float(q.mean()*100),failures=int((q<.7).sum()),high=int((q>.9).sum())),upper_bounds_computed_on_all_actual_methods=True)
    atomic(output/'SUMMARY.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default='vlm_repair_20261016_v2');p.add_argument('--stage',required=True);a=p.parse_args();setup('vlm_repair/results');r=summarize(ROOT/'runs'/a.run,a.stage);print(json.dumps(dict(status='WAIT' if r is None else 'COMPLETE',stage=a.stage)))
