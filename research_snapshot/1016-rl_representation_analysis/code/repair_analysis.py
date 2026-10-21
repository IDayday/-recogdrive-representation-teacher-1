"""Coverage-checked repair statistics and train-only gates; no final-test selection."""
from common import *
import argparse
from collections import Counter
import numpy as np
from paired_observation import save_arrays

def summarize(base,name):
    stage=base/'stages'/name;protocol=read(stage/'PROTOCOL.json');rows=read(stage/'panel.json');arms=read(stage/'arms.json');seeds=protocol['seeds']
    ids=['baseline']+[a['id'] for a in arms];by={r['token']:i for i,r in enumerate(rows)};ai={a:i for i,a in enumerate(ids)};si={j:i for i,j in enumerate(seeds)}
    shape=(len(seeds),len(rows),len(ids));data=np.full(shape+(7,),np.nan,dtype=np.float64);seen=np.zeros(shape,dtype=bool)
    fields=['score']+COMPONENTS;paths=sorted((base/'results').glob(name+'_s*.json'))
    assert len(paths)==protocol['tasks'],(name,len(paths),protocol['tasks'])
    edits=np.zeros(shape+(5,),dtype=np.float32)
    for path in paths:
        proof=read(base/'receipts'/path.name);assert proof['result_sha256']==sha(path)
        doc=read(path);assert doc['task']['stage']==name
        for r in doc['records']:
            j=si[r['seed_index']];i=by[r['token']];a=ai[r['arm']]
            assert not seen[j,i,a];seen[j,i,a]=True;data[j,i,a]=[r['score'][f] for f in fields]
            assert r['quality']==quality(r['score']['score']) and r['seed']==seed(r['token'],r['seed_index'])
            e=r.get('edit',{});g=r.get('geometry',{})
            edits[j,i,a]=[e.get('relative_edit_max',0),e.get('gate_mean',0),g.get('trajectory_displacement_mean_m',0),g.get('trajectory_displacement_max_m',0),g.get('second_difference_change_max_m',0)]
    assert seen.all() and np.isfinite(data).all()
    out=ROOT/'repair_v1/analysis'/name;out.mkdir(parents=True,exist_ok=True);np.save(out/'scores.npy',data);np.save(out/'edits.npy',edits)
    atomic(out/'rows.json',rows);atomic(out/'arms.json',arms)
    native=data[:,:,0,0];s0=np.array([r['quality'] for r in rows]);summaries=[]
    if all(r.get('cohort')=='navtest' for r in rows):s0=np.array([quality(v) for v in native[seeds.index(0)]])
    population=Counter(r['quality'] for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration')
    for a,arm in enumerate(arms,1):
        predicted=data[:,:,a,0];delta=predicted-native;failure=native<.7;high=native>.9
        active=(edits[:,:,a,0]>1e-8)|(edits[:,:,a,3]>1e-8)
        seed_results=[]
        for j,seed_index in enumerate(seeds):
            f=failure[j];h=high[j];mid=~(f|h)
            seed_results.append(dict(seed_index=seed_index,n=len(rows),baseline_mean_pdms=float(native[j].mean()*100),
                mean_pdms=float(predicted[j].mean()*100),delta_pdms=float(delta[j].mean()*100),
                failures=int(f.sum()),repaired_ge70=int((f&(predicted[j]>=.7)).sum()),repaired_gt90=int((f&(predicted[j]>.9)).sum()),
                high_quality=int(h.sum()),high_to_le90=int((h&(predicted[j]<=.9)).sum()),high_to_failure=int((h&(predicted[j]<.7)).sum()),
                new_failure_from_nonfailure=int(((~f)&(predicted[j]<.7)).sum()),intermediate=int(mid.sum()),intermediate_delta=float(delta[j,mid].mean()*100) if mid.any() else None,
                fixed_S0_failures=int((s0=='failure').sum()),fixed_S0_failures_to_gt90=int(((s0=='failure')&(predicted[j]>.9)).sum()),
                new_collisions=int(((data[j,:,0,1]==1)&(data[j,:,a,1]<1)).sum()),
                new_offroad=int(((data[j,:,0,2]==1)&(data[j,:,a,2]<1)).sum()),new_zeroes=int(((native[j]>0)&(predicted[j]==0)).sum())))
        # Reweight enriched training screen to its actual natural population.
        enriched=name in ['screen','natural_learn_screen','sensitivity_screen','budget_control','early_quality_screen']
        weighted=(sum(float(delta[:,s0==label].mean())*n/sum(population.values()) for label,n in population.items() if (s0==label).any())*100 if enriched else float(delta.mean()*100))
        sessions=np.array([r['session'] for r in rows]);unique=np.unique(sessions);gap=delta.mean(0)
        sums=np.array([gap[sessions==s].sum() for s in unique]);counts=np.array([(sessions==s).sum() for s in unique])
        rng=np.random.default_rng(20261016);draw=rng.integers(len(unique),size=(500,len(unique)));boot=sums[draw].sum(1)/counts[draw].sum(1)*100
        intervals={}
        for label,event,denominator in [
            ('repair_ge70',failure&(predicted>=.7),failure),
            ('repair_gt90',failure&(predicted>.9),failure),
            ('high_to_failure',high&(predicted<.7),high),
            ('high_to_le90',high&(predicted<=.9),high)]:
            numerator=np.array([event[:,sessions==s].sum() for s in unique],dtype=float)
            denom=np.array([denominator[:,sessions==s].sum() for s in unique],dtype=float)
            draws=numerator[draw].sum(1)/np.maximum(denom[draw].sum(1),1)
            intervals[label]=np.quantile(draws,[.025,.975]).tolist()
        summaries.append(dict(arm=arm,by_seed=seed_results,mean_delta_pdms=float(delta.mean()*100),population_weighted_screen_delta=weighted,
            session_bootstrap_delta_ci95=np.quantile(boot,[.025,.975]).tolist(),repair_rate=float(((predicted>=.7)&failure).sum()/max(failure.sum(),1)),
            session_bootstrap_rate_ci95=intervals,
            complete_repair_rate=float(((predicted>.9)&failure).sum()/max(failure.sum(),1)),high_damage_to_failure_rate=float(((predicted<.7)&high).sum()/max(high.sum(),1)),
            high_damage_le90_rate=float(((predicted<=.9)&high).sum()/max(high.sum(),1)),
            oracle_failure_gate_delta_pdms=float((delta*failure).mean()*100),
            oracle_benefit_gate_delta_pdms=float(np.maximum(delta,0).mean()*100),
            activation_rate=float(active.mean()),failure_precision_of_activation=float((active&failure).sum()/max(active.sum(),1)),
            positive_pdms_fraction_of_activation=float((active&(delta>1e-8)).sum()/max(active.sum(),1)),
            negative_pdms_fraction_of_activation=float((active&(delta< -1e-8)).sum()/max(active.sum(),1)),
            editing_relative_max=float(edits[:,:,a,0].max()),mean_gate=float(edits[:,:,a,1].mean()),
            displacement_max_m=float(edits[:,:,a,3].max()),local_bending_p95_m=float(np.quantile(edits[:,:,a,4],.95))))
    summaries.sort(key=lambda r:r['population_weighted_screen_delta'],reverse=True)
    genuine=[i+1 for i,a in enumerate(arms) if a['method'] not in ['random','random_subspace','reverse'] and not a.get('privileged_diagnostic',False) and not a.get('control',False)]
    oracle=None
    if genuine:
        best=data[:,:,[0]+genuine,0].max(2);failed=native<.7
        oracle=dict(scope='only the explicitly evaluated genuine-edit candidates plus Base; diagnostic, not deployable or a global upper bound',
            candidates=len(genuine),mean_delta_pdms=float((best-native).mean()*100),
            baseline_failures=int(failed.sum()),repaired_ge70=int((failed&(best>=.7)).sum()),repaired_gt90=int((failed&(best>.9)).sum()))
    result=dict(status='COMPLETE',time=stamp(),stage=name,protocol=protocol,coverage_exact=True,records=int(np.prod(shape)),oracle_of_tested_candidates=oracle,
        baseline_by_seed=[dict(seed=j,mean_pdms=float(native[i].mean()*100),failure=int((native[i]<.7).sum()),high=int((native[i]>.9).sum())) for i,j in enumerate(seeds)],
        summaries=summaries,interpretation='development selection only; final test remains separate')
    atomic(out/'SUMMARY.json',result);return result

def risk_threshold(layer,quantile=.995):
    nat=ROOT/'analysis/natural_route1_v1';meta=read(nat/'metadata.json');scores=np.load(nat/'scores.npy')
    select=np.array([r['subset']=='exploration' for r in meta])&(scores>.9)
    coords=np.load(nat/'coordinates_hidden.npy',mmap_mode='r');risk=[]
    with np.load(ROOT/'repair_v1/fits'/f's4_l{layer}_k8.npz') as f:
        for tok in range(8):
            z=np.array(coords[select,4,layer,tok,8:16],dtype=np.float64)
            risk.append((z-f[f'n_{tok}_risk_origin'])@f[f'n_{tok}_risk'])
    return float(np.quantile(np.stack(risk,1).max(1),quantile))

def fit_benefit_gate(base,stage_name,arm):
    src=ROOT/'repair_v1/analysis'/stage_name;rows=read(src/'rows.json');arms=read(src/'arms.json');i=next(i+1 for i,a in enumerate(arms) if a['id']==arm['id'])
    score=np.load(src/'scores.npy');target=score[0,:,i,0]-score[0,:,0,0]
    coords=np.load(ROOT/'analysis/natural_route1_v1/coordinates_hidden.npy',mmap_mode='r');indices=[r['global_index'] for r in rows]
    x=np.array(coords[indices,4,arm['layer'],:,8:16],dtype=np.float64).reshape(len(rows),-1)
    mu=x.mean(0);scale=np.maximum(x.std(0),1e-6);z=(x-mu)/scale
    pop=Counter(r['quality'] for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration');sample=Counter(r['quality'] for r in rows)
    w=np.array([pop[r['quality']]/sample[r['quality']] for r in rows]);w/=w.mean()
    intercept=float(np.average(target,weights=w));weights=np.linalg.solve(z.T@(w[:,None]*z)+len(z)*.1*np.eye(z.shape[1]),z.T@(w*(target-intercept)))
    path=ROOT/'repair_v1/gates'/f'{arm["id"]}.npz';assert not path.exists();save_arrays(path,mean=mu,scale=scale,weights=weights,intercept=intercept)
    atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),fit='exploration repair outcomes only',input='natural pre-intervention hidden coordinates',
        uses_gt_at_inference=False,uses_pdms_at_inference=False,arm=arm,sha256=sha(path)))
    return str(path.relative_to(ROOT))

def safety(name):
    """Separate immutable safety ledger derived from already verified score matrices."""
    path=ROOT/'repair_v1/analysis'/name;arms=read(path/'arms.json');data=np.load(path/'scores.npy',mmap_mode='r');result=[]
    for i,arm in enumerate(arms,1):
        row=dict(arm_id=arm['id'],by_seed=[])
        for j in range(data.shape[0]):
            values={}
            for label,field in [('collision',1),('offroad',2),('ttc',4)]:
                before=data[j,:,0,field]<1;after=data[j,:,i,field]<1
                values[label]=dict(before=int(before.sum()),after=int(after.sum()),new=int((~before&after).sum()),removed=int((before&~after).sum()),net=int(after.sum()-before.sum()))
            before=data[j,:,0,0]==0;after=data[j,:,i,0]==0
            values['zero']=dict(before=int(before.sum()),after=int(after.sum()),new=int((~before&after).sum()),removed=int((before&~after).sum()),net=int(after.sum()-before.sum()))
            values['progress_mean_change']=float((data[j,:,i,3]-data[j,:,0,3]).mean())
            row['by_seed'].append(values)
        result.append(row)
    doc=dict(status='COMPLETE',time=stamp(),stage=name,score_matrix_sha256=sha(path/'scores.npy'),records=result)
    output=path/'SAFETY.json'
    if output.exists():assert read(output)['score_matrix_sha256']==doc['score_matrix_sha256']
    else:atomic(output,doc)
    return doc

def select(base):
    combined=[]
    for name in ['screen','natural_learn_screen']:
        s=read(ROOT/'repair_v1/analysis'/name/'SUMMARY.json')
        combined.extend(dict(r,stage=name) for r in s['summaries'])
    candidates=[r for r in combined if r['arm']['method'] not in ['random','reverse','random_subspace','paired'] and not r['arm'].get('control',False)]
    chosen=[]
    # Preserve the three natural-distribution baselines, the within-scene paired direction,
    # and four conditional/learned/quality mechanisms before adding stronger alternatives.
    for method,source in [('mean','n'),('contract','n'),('ot','n'),('mean','p'),('local',None),('linear',None),('mlp',None),('quality',None)]:
        group=[r for r in candidates if r['arm']['method']==method and (source is None or r['arm']['source']==source)]
        bounded=[r for r in group if r['high_damage_to_failure_rate']<=.005]
        chosen.append(max(bounded or group,key=lambda r:r['population_weighted_screen_delta']))
    for r in sorted(candidates,key=lambda r:r['population_weighted_screen_delta'],reverse=True):
        if len(chosen)>=10:break
        if r['arm']['id'] not in {c['arm']['id'] for c in chosen}:chosen.append(r)
    selected=[];risk={}
    for r in chosen:
        a=r['arm'];selected.append(a)
        if a['steps']==[4] and 'multi_layers' not in a and 'multi_steps' not in a:
            layer=a['layer']
            if layer not in risk:risk[layer]=risk_threshold(layer)
            gate=dict(a,gate='hard',gate_threshold=risk[layer],parent=a['id']);gate['id']='risk_gate_'+digest(gate)[:12];selected.append(gate)
            bp=fit_benefit_gate(base,r['stage'],a)
            gate=dict(a,gate='benefit',benefit_path=bp,benefit_threshold=0.,parent=a['id']);gate['id']='benefit_gate_'+digest(gate)[:12];selected.append(gate)
    # A small precision curve for two strong, distinct parents, rather than every possible grid combination.
    precision_parents=[r for r in sorted(chosen,key=lambda r:r['population_weighted_screen_delta'],reverse=True)
        if r['arm']['steps']==[4] and 'multi_layers' not in r['arm'] and 'multi_steps' not in r['arm']][:2]
    for r in precision_parents:
        a=r['arm']
        for quantile in [.99,.999]:
            gate=dict(a,gate='hard',gate_threshold=risk_threshold(a['layer'],quantile),parent=a['id'],calibration_quantile=quantile)
            gate['id']='precision_gate_'+digest(gate)[:12];selected.append(gate)
        parent=next(v for v in selected if v.get('parent')==a['id'] and v['gate']=='benefit')
        gate=dict(parent,benefit_threshold=.005);gate['id']='benefit_threshold_'+digest(gate)[:12];selected.append(gate)
    # Matched null and reverse controls accompany the selected family.
    for method in ['random','random_subspace','reverse']:
        selected.append(next(r['arm'] for r in combined if r['arm']['method']==method and r['arm']['layer']==17))
    atomic(ROOT/'repair_v1/SELECTION.json',dict(time=stamp(),rule='one per mechanism with <=0.5% damage when available, then best population-reweighted screen delta; no validation used',
        chosen=chosen,risk_thresholds=risk,validation_arms=selected,validation_seeds=[0,1,2]))
    return selected

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['summary','select','safety']);p.add_argument('--stage');args=p.parse_args();setup('repair/analysis');compatibility()
    base=ROOT/'runs'/read(ROOT/'repair_v1/ACTIVE_RUN.json')['run']
    if args.command=='summary':result=summarize(base,args.stage);print(json.dumps(dict(stage=args.stage,arms=len(result['summaries']),records=result['records'])))
    elif args.command=='select':print(json.dumps(dict(arms=len(select(base)))))
    else:print(json.dumps(dict(safety_records=len(safety(args.stage)['records']))))
