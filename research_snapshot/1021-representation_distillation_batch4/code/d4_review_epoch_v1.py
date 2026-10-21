"""Validate epoch development records and expose fitting/retention diagnostics."""
from d4_common_v2 import *
import argparse


def main(a):
    setup('development_review/'+a.group,threads=4)
    import numpy as np
    from d4_evaluate_student_v1 import population
    from d4_compare_students_v1 import paired
    run=ROOT/'runs'/('distillation_main_v4_'+a.group);config_path=ROOT/'configs/distillation_main_v4'/(a.group+'.json');config=read(config_path)
    folder=run/'development'/('epoch%02d'%a.epoch);summary_path=folder/'SUMMARY.json';summary=read(summary_path)
    assert summary['status']=='PASS_DEVELOPMENT_PANEL' and not summary['GT_used'] and not summary['student_inference_teacher_or_PDMS_input']
    expected=read(config['development_indices']);assert sha(config['development_indices'])==config['development_indices_sha256']
    rows,prior,_=population('navtrain');geometry=read(ROOT/'analysis/teacher_geometry_v1/CASE_METADATA.json');g={v['index']:v for v in geometry}
    records=[]
    for reference in summary['source_rank_files']:
        path=ROOT/reference['path'];assert sha(path)==reference['sha256'];part=read(path)
        assert part['status']=='PASS_DEVELOPMENT_NATIVE_INFERENCE_AND_FRESH_SCORE' and not part['GT_used']
        records.extend(part['cases'])
    records.sort(key=lambda x:x['global_index']);assert [r['global_index'] for r in records]==sorted(expected)
    quality=np.asarray([r['quality'] for r in records],dtype=np.float64);baseline=np.asarray([r['Base_quality'] for r in records],dtype=np.float64)
    assert quality.shape==baseline.shape==(len(expected),5,7) and np.isfinite(quality).all() and np.isfinite(baseline).all()
    assert (quality>=0).all() and (quality<=1+1e-8).all()
    assert np.max(np.abs(quality[:,:,1]*quality[:,:,2]*(5*quality[:,:,4]+5*quality[:,:,3]+2*quality[:,:,5])/12-quality[:,:,0]))<1e-8
    for r,b in zip(records,baseline):
        row=rows[r['global_index']];assert row['token']==r['token'] and row['session']==r['session'] and row['subset']=='validation' and row['pool']==r['pool']
        assert np.array_equal(b,prior['scores'][r['global_index'],0])
        assert np.asarray(r['trajectories']).shape==(5,8,3) and np.isfinite(r['trajectories']).all()
        assert np.isfinite(r['interface_MSE']) and r['interface_MSE']>=0
    assert abs(quality[:,:,0].mean()*100-summary['PDMS'])<1e-10
    assert abs(baseline[:,:,0].mean()*100-summary['Base_PDMS'])<1e-10
    subsets={'all':list(range(len(records)))}
    for pool in ['I','P','E']:
        indices=[i for i,r in enumerate(records) if r['pool']==pool]
        if indices:subsets['pool_'+pool]=indices
    for tag,hard in [('hard_I',True),('other_I',False)]:
        indices=[i for i,r in enumerate(records) if r['pool']=='I' and g[r['global_index']]['hard']==hard]
        if indices:subsets[tag]=indices
    values={}
    for name,indices in subsets.items():
        before=float(np.mean([g[records[i]['global_index']]['initial_H_MSE'] for i in indices]));after=float(np.mean([records[i]['interface_MSE'] for i in indices]))
        ref=np.asarray([prior['scores'][records[i]['global_index'],int(prior['selected'][records[i]['global_index'],5]),:,0] for i in indices])
        values[name]=dict(student_vs_Base=paired(quality,baseline,records,indices,list(range(5)))['S0S4'],
            Base_initial_interface_MSE=before,student_interface_MSE=after,ratio_to_Base_initial_MSE=after/before if before>0 else None,
            fixed_R2_teacher_PDMS=float(ref.mean()*100))
    result=dict(status='REVIEWED_EPOCH_DEVELOPMENT_DIAGNOSTIC',time=stamp(),group=a.group,epoch=a.epoch,cases=len(records),
        source_summary=str(summary_path.relative_to(ROOT)),source_summary_sha256=sha(summary_path),configuration_sha256=sha(config_path),
        results=values,development_panel_is_not_full_validation=True,GT_used=False,test_or_new_noise_used=False,
        first_round_training_configuration_unchanged=True,not_a_final_student_result=True)
    if a.acknowledge:
        target=ROOT/'provenance/training_epoch_reviews_v1'/(config['run_id']+'_epoch%02d.json'%a.epoch)
        assert not target.exists();atomic(target,result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['H','T','HT'],required=True);p.add_argument('--epoch',type=int,required=True)
    p.add_argument('--acknowledge',action='store_true');main(p.parse_args())
