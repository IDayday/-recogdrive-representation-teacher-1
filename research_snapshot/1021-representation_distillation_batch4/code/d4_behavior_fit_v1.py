"""Offline trajectory fitting diagnostics; never a teacher or model selector."""
from d4_common_v2 import *
import argparse


def trajectory_errors(prediction,target):
    import numpy as np
    x=np.asarray(prediction,dtype=np.float64);y=np.asarray(target,dtype=np.float64)
    assert x.shape==y.shape and x.ndim==4 and x.shape[-2:]==(8,3)
    assert np.isfinite(x).all() and np.isfinite(y).all()
    absolute=np.abs((x[...,:2]-y[...,:2])/np.asarray([40.,10.]))
    position=np.where(absolute<1,.5*absolute**2,absolute-.5).mean(axis=(-1,-2))
    yaw=x[...,2]-y[...,2];heading=(1-np.cos(yaw)).mean(-1)
    displacement=np.linalg.norm(x[...,:2]-y[...,:2],axis=-1)
    return dict(training_proxy=position+.1*heading,position_smooth_L1=position,heading_one_minus_cos=heading,
        ADE_metres=displacement.mean(-1),FDE_metres=displacement[...,-1],
        wrapped_heading_error_radians=np.abs(np.arctan2(np.sin(yaw),np.cos(yaw))).mean(-1))


def diagnostics(student,baseline,target,quality,Base_quality,rows,groups):
    import numpy as np
    learned=trajectory_errors(student,target);original=trajectory_errors(baseline,target)
    quality=np.asarray(quality,dtype=np.float64);Base_quality=np.asarray(Base_quality,dtype=np.float64)
    assert quality.shape==Base_quality.shape==student.shape[:2]+(7,)
    qdelta=quality[:,:,0]-Base_quality[:,:,0];proxy_gain=original['training_proxy']-learned['training_proxy'];result={}
    for name,indices in groups.items():
        if not indices:continue
        ix=np.asarray(indices,dtype=np.int64);pg=proxy_gain[ix];dq=qdelta[ix];scene_pg=pg.mean(1);scene_dq=dq.mean(1)
        result[name]=dict(cases=len(ix),outputs=int(dq.size),
            Base_errors_to_teacher={k:float(v[ix].mean()) for k,v in original.items()},
            student_errors_to_teacher={k:float(v[ix].mean()) for k,v in learned.items()},
            student_PDMS=float(quality[ix,:,0].mean()*100),Base_PDMS=float(Base_quality[ix,:,0].mean()*100),PDMS_gain=float(dq.mean()*100),
            proxy_improved_outputs=int((pg>0).sum()),proxy_worsened_outputs=int((pg<0).sum()),
            proxy_improved_but_PDMS_worsened_outputs=int(((pg>0)&(dq<0)).sum()),
            proxy_improved_and_PDMS_improved_outputs=int(((pg>0)&(dq>0)).sum()),
            proxy_improved_PDMS_unchanged_outputs=int(((pg>0)&(dq==0)).sum()),
            proxy_improved_mean_scenes=int((scene_pg>0).sum()),
            proxy_improved_but_PDMS_worsened_mean_scenes=int(((scene_pg>0)&(scene_dq<0)).sum()))
    return dict(metrics=result,scope='Original S0-S4 only; actual fixed R2 trajectory targets; no GT',
        proxies_calculated_independently_in_numpy_float64=True,proxy_definition_matches_training=True,
        diagnostic_does_not_select_candidates_checkpoints_or_teacher=True)


def development(group,epoch):
    import numpy as np
    from d4_evaluate_student_v1 import population
    run=ROOT/'runs'/('distillation_main_v4_'+group);folder=run/'development'/('epoch%02d'%epoch);summary=read(folder/'SUMMARY.json')
    assert summary['status']=='PASS_DEVELOPMENT_PANEL';records=[]
    for source in summary['source_rank_files']:
        assert sha(ROOT/source['path'])==source['sha256'];records.extend(read(ROOT/source['path'])['cases'])
    records.sort(key=lambda r:r['global_index']);rows,prior,_=population('navtrain');indices=np.asarray([r['global_index'] for r in records],dtype=np.int64)
    assert len(indices)==summary['cases'] and len(set(indices))==len(indices)
    assert all(rows[i]['subset']=='validation' and rows[i]['token']==r['token'] for i,r in zip(indices,records))
    student=np.asarray([r['trajectories'] for r in records],dtype=np.float32)
    baseline=np.asarray(prior['trajectories'][indices,0]);target=np.asarray(prior['trajectories'][indices,prior['selected'][indices,5]])
    quality=np.asarray([r['quality'] for r in records],dtype=np.float64);base_quality=np.asarray(prior['scores'][indices,0])
    subsets={'all':list(range(len(records)))}
    for pool in ['I','P','E']:
        ix=[i for i,r in enumerate(records) if r['pool']==pool]
        if ix:subsets['pool_'+pool]=ix
    result=diagnostics(student,baseline,target,quality,base_quality,records,subsets)
    proof=dict(status='PASS_DEVELOPMENT_TRAJECTORY_FITTING_DIAGNOSTIC',time=stamp(),group=group,epoch=epoch,
        source_summary_sha256=sha(folder/'SUMMARY.json'),results=result,not_a_full_validation_or_final_student_result=True,GT_used=False)
    path=ROOT/'analysis/development_behavior_fit_v1'/(group+'_epoch%02d.json'%epoch);assert not path.exists();atomic(path,proof)
    print(json.dumps(dict(status=proof['status'],group=group,epoch=epoch,metrics=result['metrics']),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['H','T','HT'],required=True);p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
    setup('behavior_fit/'+a.group,threads=4);development(a.group,a.epoch)
