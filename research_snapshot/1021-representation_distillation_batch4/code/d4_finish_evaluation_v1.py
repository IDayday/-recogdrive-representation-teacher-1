"""Accept audited coverage and report scenes/sessions, old and unseen noises."""
from d4_common_v2 import *
import argparse
import math


def summarize(q,b,t,rows,positions,noises,interface_mse):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    ix=np.asarray(positions,dtype=np.int64);x=np.asarray(q[ix]);base=np.asarray(b[ix]);old=np.asarray(t[ix]);n=len(ix)
    sessions=np.asarray([rows[int(i)]['session'] for i in ix]);unique,session=np.unique(sessions,return_inverse=True)
    rng=np.random.default_rng(2026102107);weights=rng.multinomial(len(unique),np.full(len(unique),1/len(unique)),size=2000)
    sizes=np.bincount(session);groups={}
    for label,allowed in [('S0S4',range(5)),('S5S9',range(5,10)),('all_evaluated',noises)]:
        selected=[k for k,j in enumerate(noises) if j in allowed]
        if not selected:continue
        quality=x[:,selected];before=base[:,selected];delta=quality[:,:,0]-before[:,:,0];scene_delta=delta.mean(1)
        sums=np.bincount(session,weights=scene_delta);bootstrap=(weights@sums)/(weights@sizes)*100
        safety={}
        for field in ['no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound']:
            col=FIELDS.index(field);new=(quality[:,:,col]<1)&(before[:,:,col]>=1);removed=(quality[:,:,col]>=1)&(before[:,:,col]<1)
            safety[field]=dict(new=int(new.sum()),removed=int(removed.sum()),net=int(new.sum()-removed.sum()))
        value=dict(cases=n,outputs=n*len(selected),sessions=len(unique),noises=[noises[k] for k in selected],
            PDMS=float(quality[:,:,0].mean()*100),Base_PDMS=float(before[:,:,0].mean()*100),gain=float(delta.mean()*100),
            gain_session_bootstrap_CI95=np.quantile(bootstrap,[.025,.975]).tolist(),
            PDMS_by_noise=(quality[:,:,0].mean(0)*100).tolist(),Base_PDMS_by_noise=(before[:,:,0].mean(0)*100).tolist(),
            score_components={name:float(quality[:,:,i].mean()) for i,name in enumerate(FIELDS)},safety_events=safety,
            positive_mean_scenes=int((scene_delta>0).sum()),negative_mean_scenes=int((scene_delta<0).sum()),
            high_outputs_above90=int((quality[:,:,0]>.9).sum()),failure_outputs_below70=int((quality[:,:,0]<.7).sum()),zero_outputs=int((quality[:,:,0]==0).sum()),
            Base_high_to_not_high=int(((before[:,:,0]>.9)&(quality[:,:,0]<=.9)).sum()),Base_high_to_failure=int(((before[:,:,0]>.9)&(quality[:,:,0]<.7)).sum()))
        if label=='S0S4' and set(range(5))<=set(noises):
            teacher_mean=float(old[:,:,0].mean()*100);gain=teacher_mean-value['Base_PDMS']
            value.update(fixed_R2_teacher_PDMS=teacher_mean,fixed_R2_teacher_gain=gain,
                teacher_gain_absorption=value['gain']/gain if abs(gain)>1e-6 else None,
                absorption_not_a_theoretical_upper_bound=True)
        groups[label]=value
    return dict(cases=n,mean_interface_MSE=float(np.asarray(interface_mse[ix]).mean()),noise_groups=groups,
        confidence_intervals_exclude_training_seed_uncertainty=True)


def main(a):
    setup('evaluation_merge/'+Path(a.stage).name,threads=4)
    import numpy as np
    from d4_evaluate_student_v1 import population
    stage=ROOT/a.stage;spec=read(stage/'SPECIFICATION.json');template=spec['task_template']
    assert (stage/'AUDIT_COMPLETE.json').exists() and not (stage/'AGENT_ACCEPTANCE.json').exists()
    assert not list((stage/'failures').glob('*.json')) and not list((stage/'audit/failures').glob('*.json'))
    expected=read(spec['indices_path']) if 'indices_path' in spec else list(range(spec['case_count']))
    if 'indices_path' in spec:assert sha(spec['indices_path'])==spec['indices_sha256']
    assert len(expected)==spec['case_count'] and len(set(expected))==len(expected)
    mapping={index:position for position,index in enumerate(expected)};count=len(expected);j=len(template['noises'])
    target=ROOT/'analysis/full_student_evaluation_v1'/stage.name;assert not target.exists();target.mkdir(parents=True)
    q=np.lib.format.open_memmap(target/'student_quality.npy',mode='w+',dtype=np.float64,shape=(count,j,7))
    b=np.lib.format.open_memmap(target/'Base_quality.npy',mode='w+',dtype=np.float64,shape=(count,j,7))
    t=np.lib.format.open_memmap(target/'teacher_R2_reference_S0S4.npy',mode='w+',dtype=np.float64,shape=(count,5,7))
    trajectory=np.lib.format.open_memmap(target/'student_trajectories.npy',mode='w+',dtype=np.float32,shape=(count,j,8,3))
    mse=np.lib.format.open_memmap(target/'interface_MSE.npy',mode='w+',dtype=np.float64,shape=(count,))
    seen=np.zeros(count,dtype=bool);index_rows=[None]*count;sources=[]
    proofs=list((stage/'audit/shards').glob('*.json'));assert len(proofs)==math.ceil(count/spec['chunk_size'])
    for path in sorted(proofs):
        proof=read(path);assert proof['status']=='PASS_INDEPENDENT_STUDENT_EVALUATION_CPU_AUDIT'
        assert proof['checkpoint_sha256']==template['checkpoint_sha256'] and proof['training_config_sha256']==template['training_config_sha256']
        receipt_path=ROOT/proof['receipt_path'];assert sha(receipt_path)==proof['receipt_sha256']
        source=ROOT/proof['array']['path'];assert sha(source)==proof['array']['sha256']
        with np.load(source,allow_pickle=False) as z:
            assert z['noise_indices'].tolist()==template['noises']
            positions=np.asarray([mapping[int(i)] for i in z['indices']],dtype=np.int64);assert not seen[positions].any()
            q[positions]=z['student_quality'];b[positions]=z['Base_quality'];t[positions]=z['teacher_R2_reference_S0S4'];trajectory[positions]=z['student_trajectories'];mse[positions]=z['interface_MSE'];seen[positions]=True
        assert [c['global_index'] for c in proof['cases']]==[expected[i] for i in positions]
        for position,case in zip(positions,proof['cases']):index_rows[int(position)]=case
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
    assert seen.all()
    for array in [q,b,t,trajectory,mse]:array.flush()
    source_rows,prior,_=population(template['cohort']);groups={}
    for position,row in enumerate(index_rows):
        index=row['global_index'];assert source_rows[index]['token']==row['token']
        if row['pool']=='test_not_training':
            baseline=prior['scores'][index,0,:,0];teacher=t[position,:,0]
            delta=math.fsum(float(x-y) for x,y in zip(teacher,baseline))/5;base_mean=math.fsum(float(x) for x in baseline)/5
            row['reference_pool']='I' if delta>0 else 'P' if delta==0 and base_mean>.9 else 'E' if delta==0 else 'numerical_reference_tie_requires_note'
        else:row['reference_pool']=row['pool']
        old_base=np.asarray(prior['scores'][index,0,:,0]);row['Base_old_five_any_below70']=bool((old_base<.7).any())
        row['Base_old_five_mean_above90']=bool(old_base.mean()>.9)
    groups['navtrain_all' if template['cohort']=='navtrain' and count==103288 else stage.name]=list(range(count))
    for subset in ['exploration','validation']:
        positions=[i for i,row in enumerate(index_rows) if row['subset']==subset]
        if positions:groups[subset]=positions
    for pool in ['I','P','E','numerical_reference_tie_requires_note']:
        positions=[i for i,row in enumerate(index_rows) if row['reference_pool']==pool]
        if positions:groups['reference_pool_'+pool]=positions
    for name,condition in [('Base_old_five_any_below70',lambda r:r['Base_old_five_any_below70']),('Base_old_five_mean_above90',lambda r:r['Base_old_five_mean_above90'])]:
        positions=[i for i,row in enumerate(index_rows) if condition(row)]
        if positions:groups[name]=positions
    results={name:summarize(q,b,t,index_rows,positions,template['noises'],mse) for name,positions in groups.items()}
    atomic(target/'CASE_INDEX.json',index_rows)
    artifacts={name:dict(path=str((target/name).relative_to(ROOT)),sha256=sha(target/name)) for name in ['student_quality.npy','Base_quality.npy','teacher_R2_reference_S0S4.npy','student_trajectories.npy','interface_MSE.npy','CASE_INDEX.json']}
    summary=dict(status='PASS_ENGINEERING_STUDENT_EVALUATION' if spec.get('engineering_only') else 'PASS_COMPLETE_AUDITED_STUDENT_EVALUATION',time=stamp(),stage=a.stage,cases=count,cohort=template['cohort'],noises=template['noises'],
        model_id=template['model_id'],model_roles=spec['model_roles'],checkpoint_sha256=template['checkpoint_sha256'],training_config_sha256=template['training_config_sha256'],
        results=results,artifacts=artifacts,sources=sources,GT_used=False,test_used_for_model_selection=False,
        teacher_reference_means_S0S4_only=True,student_inference_requires_teacher_or_scoring=False)
    atomic(target/'SUMMARY.json',summary)
    atomic(stage/'AGENT_ACCEPTANCE.json',dict(status=summary['status'],time=stamp(),summary=str((target/'SUMMARY.json').relative_to(ROOT)),summary_sha256=sha(target/'SUMMARY.json')))
    print(json.dumps(dict(status=summary['status'],cases=count,model_id=template['model_id'],results={name:{k:round(v['PDMS'],6) for k,v in result['noise_groups'].items()} for name,result in results.items()})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
