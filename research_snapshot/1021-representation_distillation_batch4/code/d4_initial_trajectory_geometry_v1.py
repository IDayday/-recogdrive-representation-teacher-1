"""Measure initial trajectory supervision from immutable paired teacher outputs."""
from d4_common_v2 import *


def main():
    setup('initial_trajectory_geometry_v1',threads=4)
    import numpy as np
    from d4_behavior_fit_v1 import trajectory_errors
    from d4_evaluate_student_v1 import population
    rows,prior,_=population('navtrain');geometry=read(ROOT/'analysis/teacher_geometry_v1/CASE_METADATA.json')
    assert [v['index'] for v in geometry]==list(range(len(rows)))
    count=len(rows);errors={};chunk=1024
    for start in range(0,count,chunk):
        ix=np.arange(start,min(start+chunk,count),dtype=np.int64)
        baseline=np.asarray(prior['trajectories'][ix,0]);teacher=np.asarray(prior['trajectories'][ix,prior['selected'][ix,5]])
        local=trajectory_errors(baseline,teacher)
        for key,value in local.items():
            if key not in errors:errors[key]=np.empty((count,5),dtype=np.float64)
            errors[key][ix]=value
    groups={};fractions=[0,.25,.5,.75,.9,.95,.99,1]
    for subset in ['exploration','validation']:
        for label,condition in [('training_I_P',lambda row,g:row['pool'] in ['I','P']),('I',lambda row,g:row['pool']=='I'),
            ('P',lambda row,g:row['pool']=='P'),('E',lambda row,g:row['pool']=='E'),
            ('hard_I',lambda row,g:row['pool']=='I' and g['hard']),('other_I',lambda row,g:row['pool']=='I' and not g['hard'])]:
            indices=np.asarray([i for i,(row,g) in enumerate(zip(rows,geometry)) if row['subset']==subset and condition(row,g)],dtype=np.int64)
            if len(indices)==0:continue
            metrics={key:dict(mean=float(value[indices].mean()),scene_mean_quantiles=np.quantile(value[indices].mean(1),fractions).tolist()) for key,value in errors.items()}
            if label=='P':assert all(np.count_nonzero(value[indices])==0 for value in errors.values())
            groups[subset+'_'+label]=dict(cases=len(indices),metrics=metrics,training_proxy_loss_mass=float(errors['training_proxy'][indices].sum()),
                teacher_PDMS_gain_mass=float(sum(geometry[int(i)]['gain'] for i in indices)))
        hard=groups[subset+'_hard_I'];all_I=groups[subset+'_I']
        hard['share_of_I_initial_trajectory_proxy_loss']=hard['training_proxy_loss_mass']/all_I['training_proxy_loss_mass']
        hard['share_of_I_teacher_PDMS_gain']=hard['teacher_PDMS_gain_mass']/all_I['teacher_PDMS_gain_mass']
    proof=dict(status='PASS_INITIAL_PAIRED_TRAJECTORY_SUPERVISION_GEOMETRY',time=stamp(),groups=groups,quantile_levels=fractions,
        initial_loss_mass_is_not_gradient_mass=True,all_P_trajectory_targets_exact_Base=True,GT_used=False,
        source='Immutable first42 raw scores/trajectories and R2 selections; no model inference',
        training_configuration_unchanged=True,test_used=False)
    target=ROOT/'analysis/initial_trajectory_geometry_v1/SUMMARY.json';assert not target.exists();atomic(target,proof)
    print(json.dumps(dict(status=proof['status'],hard_train=groups['exploration_hard_I'],all_train_I_P=groups['exploration_training_I_P']),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
