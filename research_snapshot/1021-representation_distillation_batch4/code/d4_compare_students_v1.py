"""Paired H/T/HT comparisons on exactly matched scenes and action-noise draws."""
from d4_common_v2 import *
import argparse


def paired(left,right,rows,indices,noises):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    ix=np.asarray(indices,dtype=np.int64);a=np.asarray(left[ix]);b=np.asarray(right[ix])
    sessions=np.asarray([rows[int(i)]['session'] for i in ix]);unique,inverse=np.unique(sessions,return_inverse=True)
    counts=np.bincount(inverse);weights=np.random.default_rng(2026102107).multinomial(len(unique),np.full(len(unique),1/len(unique)),size=2000)
    result={}
    for tag,allowed in [('S0S4',range(5)),('S5S9',range(5,10)),('all_evaluated',noises)]:
        js=[k for k,j in enumerate(noises) if j in allowed]
        if not js:continue
        x=a[:,js];y=b[:,js];delta=x[:,:,0]-y[:,:,0];per_scene=delta.mean(1)
        sums=np.bincount(inverse,weights=per_scene);bootstrap=(weights@sums)/(weights@counts)*100
        safety={}
        for field in ['no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound']:
            k=FIELDS.index(field)
            safety[field]=dict(left_bad=int((x[:,:,k]<1).sum()),right_bad=int((y[:,:,k]<1).sum()),
                new=int(((x[:,:,k]<1)&(y[:,:,k]>=1)).sum()),removed=int(((x[:,:,k]>=1)&(y[:,:,k]<1)).sum()))
        result[tag]=dict(cases=len(ix),sessions=len(unique),outputs=len(ix)*len(js),noises=[noises[k] for k in js],
            left_PDMS=float(x[:,:,0].mean()*100),right_PDMS=float(y[:,:,0].mean()*100),difference=float(delta.mean()*100),
            difference_session_bootstrap_CI95=np.quantile(bootstrap,[.025,.975]).tolist(),
            positive_mean_scenes=int((per_scene>0).sum()),negative_mean_scenes=int((per_scene<0).sum()),
            safety_events=safety,zero_count_difference=int((x[:,:,0]==0).sum()-(y[:,:,0]==0).sum()),
            failure_below70_count_difference=int((x[:,:,0]<.7).sum()-(y[:,:,0]<.7).sum()),
            high_above90_count_difference=int((x[:,:,0]>.9).sum()-(y[:,:,0]>.9).sum()))
    return result


def model_for(group,role):
    frozen=read(ROOT/'runs'/('FROZEN_EVALUATION_MODELS_'+group+'.json'))
    values=[m for m in frozen['models'] if role in m['roles']];assert len(values)==1
    return values[0]


def load(group,role,scope):
    import numpy as np
    model=model_for(group,role);folder=ROOT/'analysis/full_student_evaluation_v1'/(model['id']+'_'+scope)
    source=folder/'SUMMARY.json';summary=read(source);assert summary['status']=='PASS_COMPLETE_AUDITED_STUDENT_EVALUATION'
    assert summary['checkpoint_sha256']==model['checkpoint']['sha256'] and role in summary['model_roles']
    arrays={}
    for name in ['student_quality.npy','Base_quality.npy','student_trajectories.npy','interface_MSE.npy','CASE_INDEX.json']:
        value=summary['artifacts'][name];path=ROOT/value['path'];assert sha(path)==value['sha256']
        arrays[name]=read(path) if name.endswith('.json') else np.load(path,mmap_mode='r',allow_pickle=False)
    return dict(model=model,source=dict(path=str(source.relative_to(ROOT)),sha256=sha(source)),summary=summary,arrays=arrays)


def main(a):
    setup('cross_group_comparison_v1',threads=4)
    import numpy as np
    for group in ['H','T','HT']:
        proof=read(ROOT/'runs'/('GROUP_COMPUTE_COMPLETE_'+group+'.json'))
        assert proof['status']=='PASS_ALL_FROZEN_STUDENT_COMPUTE_COMPLETE'
    geometry=read(ROOT/'analysis/teacher_geometry_v1/CASE_METADATA.json')
    geometry_by_index={row['index']:row for row in geometry};results={};sources=[]
    for role in ['primary_final','secondary_development_best']:
        results[role]={}
        for scope in ['navtrain_S0S4','validation_S5S9','navtest_S0S9']:
            groups={g:load(g,role,scope) for g in ['H','T','HT']};common=groups['H'];rows=common['arrays']['CASE_INDEX.json'];noises=common['summary']['noises']
            identity=[(r['global_index'],r['token'],r['session'],r['subset'],r['reference_pool']) for r in rows]
            for other in groups.values():
                assert [(r['global_index'],r['token'],r['session'],r['subset'],r['reference_pool']) for r in other['arrays']['CASE_INDEX.json']]==identity
                assert other['summary']['noises']==noises
                assert np.array_equal(other['arrays']['Base_quality.npy'],common['arrays']['Base_quality.npy'])
                sources.append(dict(group=other['model']['group'],role=role,scope=scope,model_id=other['model']['id'],**other['source']))
            subsets={'all':list(range(len(rows)))}
            for subset in ['exploration','validation']:
                ix=[i for i,r in enumerate(rows) if r['subset']==subset]
                if ix:subsets[subset]=ix
            for pool in ['I','P','E']:
                ix=[i for i,r in enumerate(rows) if r['reference_pool']==pool]
                if ix:subsets['pool_'+pool]=ix
                for subset in ['exploration','validation']:
                    ix=[i for i,r in enumerate(rows) if r['reference_pool']==pool and r['subset']==subset]
                    if ix:subsets[subset+'_pool_'+pool]=ix
            for name,condition in [('Base_any_below70',lambda r:r['Base_old_five_any_below70']),
                ('Base_mean_above90',lambda r:r['Base_old_five_mean_above90']),
                ('hard_I',lambda r:r['reference_pool']=='I' and r['Base_old_five_any_below70']),
                ('other_I',lambda r:r['reference_pool']=='I' and not r['Base_old_five_any_below70'])]:
                ix=[i for i,r in enumerate(rows) if condition(r)]
                if ix:subsets[name]=ix
            contrasts={}
            for left,right in [('HT','T'),('H','T'),('HT','H')]:
                contrasts[left+'_minus_'+right]={name:paired(groups[left]['arrays']['student_quality.npy'],groups[right]['arrays']['student_quality.npy'],rows,ix,noises)
                    for name,ix in subsets.items()}
            fitting={}
            if common['summary']['cohort']=='navtrain':
                initial=np.asarray([geometry_by_index[r['global_index']]['initial_H_MSE'] for r in rows],dtype=np.float64)
                for name,ix in subsets.items():
                    before=float(initial[ix].mean());fitting[name]=dict(cases=len(ix),Base_initial_interface_MSE=before,
                        students={g:dict(interface_MSE=float(v['arrays']['interface_MSE.npy'][ix].mean()),
                            ratio_to_Base_initial_MSE=float(v['arrays']['interface_MSE.npy'][ix].mean()/before) if before>0 else None)
                            for g,v in groups.items()})
            trajectory_fitting={}
            if set(range(5))<=set(noises):
                from d4_behavior_fit_v1 import diagnostics
                from d4_evaluate_student_v1 import population
                _,prior,_=population(common['summary']['cohort'])
                indices=np.asarray([row['global_index'] for row in rows],dtype=np.int64)
                baseline_trajectories=np.asarray(prior['trajectories'][indices,0])
                teacher_trajectories=np.asarray(prior['trajectories'][indices,prior['selected'][indices,5]])
                old=[noises.index(j) for j in range(5)]
                trajectory_fitting={g:diagnostics(np.asarray(v['arrays']['student_trajectories.npy'])[:,old],baseline_trajectories,teacher_trajectories,
                    np.asarray(v['arrays']['student_quality.npy'])[:,old],np.asarray(v['arrays']['Base_quality.npy'])[:,old],rows,subsets)
                    for g,v in groups.items()}
            results[role][scope]=dict(contrasts=contrasts,interface_fitting=fitting,trajectory_fitting_to_fixed_R2=trajectory_fitting,
                model_ids={g:v['model']['id'] for g,v in groups.items()},
                checkpoint_steps={g:v['model']['checkpoint']['global_step'] for g,v in groups.items()},
                primary_equal_exposure=role=='primary_final',secondary_may_select_different_training_steps=role!='primary_final')
    target=ROOT/'analysis/distillation_comparison_v1/SUMMARY.json';assert not target.exists()
    proof=dict(status='PASS_COMPLETE_PAIRED_H_T_HT_COMPARISON',time=stamp(),results=results,sources=sources,
        one_training_initialization_seed=2026102101,CI_covers_session_sampling_not_training_seed_variation=True,
        teacher_source='first42_frozen_R2',GT_used=False,student_inference_uses_teacher_or_PDMS=False,
        later_sampling_and_training_scope_controls_not_included=True)
    atomic(target,proof);print(json.dumps(dict(status=proof['status'],path=str(target.relative_to(ROOT)))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();main(p.parse_args())
