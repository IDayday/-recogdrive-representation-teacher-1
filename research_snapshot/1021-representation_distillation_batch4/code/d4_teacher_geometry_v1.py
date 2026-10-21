"""Observe fixed teacher label scale versus benefit; do not change any run."""
from d4_common_v2 import *
from concurrent.futures import ThreadPoolExecutor
import traceback


def main():
    setup('teacher_geometry_v1',threads=2)
    import numpy as np
    from scipy.stats import spearmanr
    rows=read(ROOT/'manifests/R2_TRAINING_SCENES_V2.json')
    index=read(ROOT/'analysis/full_context_replay_v1/CASE_INDEX.json')
    assert len(index)==len(rows)==103288
    def fetch(ref):
        path=ROOT/ref['path'];assert sha(path)==ref['record_sha256'];r=read(path);i=r['global_index'];row=rows[i]
        assert row['token']==r['token'] and r['Base_interface_squared_sum']>0
        assert row['pool']!='I' or r['teacher_residual_squared_sum']>0
        return dict(index=i,pool=row['pool'],subset=row['subset'],candidate=row['teacher_candidate'],gain=row['gain']*100,
            hard=row['Base_any_below70'],Base_PDMS=row['Base_mean']*100,full_tokens=r['full_tokens'],
            initial_H_MSE=r['teacher_residual_squared_sum']/(r['full_tokens']*384),
            teacher_relative_edit=float((r['teacher_residual_squared_sum']/r['Base_interface_squared_sum'])**.5))
    with ThreadPoolExecutor(max_workers=4) as pool:values=list(pool.map(fetch,index))
    values.sort(key=lambda r:r['index']);assert [r['index'] for r in values]==list(range(len(rows)))
    assert all(v['initial_H_MSE']==0 for v in values if v['pool']=='P')
    levels=[0,.25,.5,.75,.9,.99,1]
    def stats(items):
        gain=np.asarray([v['gain'] for v in items]);error=np.asarray([v['initial_H_MSE'] for v in items]);relative=np.asarray([v['teacher_relative_edit'] for v in items])
        correlation=spearmanr(gain,error).statistic if len(items)>1 and np.ptp(gain)>0 and np.ptp(error)>0 else None
        return dict(cases=len(items),mean_gain=float(gain.mean()),gain_quantiles=np.quantile(gain,levels).tolist(),initial_H_MSE_mean=float(error.mean()),
            initial_H_MSE_quantiles=np.quantile(error,levels).tolist(),teacher_relative_edit_quantiles=np.quantile(relative,levels).tolist(),
            gain_vs_initial_H_error_spearman=None if correlation is None or not np.isfinite(correlation) else float(correlation))
    groups={}
    for subset in ['exploration','validation']:
        selected=[v for v in values if v['subset']==subset]
        for pool in ['I','P','E']:
            items=[v for v in selected if v['pool']==pool]
            if items:groups[subset+'_'+pool]=stats(items)
        learning=[v for v in selected if v['pool'] in ['I','P']]
        total_error=sum(v['initial_H_MSE'] for v in learning);total_gain=sum(v['gain'] for v in learning)
        for tag,predicate in [('hard_I',lambda v:v['pool']=='I' and v['hard']),('other_I',lambda v:v['pool']=='I' and not v['hard']),('P',lambda v:v['pool']=='P')]:
            items=[v for v in learning if predicate(v)]
            if items:groups[subset+'_training_role_'+tag]=dict(stats(items),initial_H_loss_mass_fraction=sum(v['initial_H_MSE'] for v in items)/total_error,
                teacher_gain_mass_fraction=sum(v['gain'] for v in items)/total_gain)
    early=[]
    for group in ['H','T','HT']:
        path=ROOT/'runs'/('distillation_main_v4_'+group)/'EARLY_PHASE_READY.json'
        if not path.exists():continue
        ready=read(path);records=[]
        for source in ready['development']['source_rank_files']:records.extend(read(ROOT/source['path'])['cases'])
        for pool in ['all','I','P','E']:
            items=[r for r in records if pool=='all' or r['pool']==pool]
            if not items:continue
            early.append(dict(group=group,pool=pool,cases=len(items),Base_initial_H_MSE=float(np.mean([values[r['global_index']]['initial_H_MSE'] for r in items])),
                student_H_MSE=float(np.mean([r['interface_MSE'] for r in items])),diagnostic_only=True))
    target=ROOT/'analysis/teacher_geometry_v1';atomic(target/'SUMMARY.json',dict(status='COMPLETE_OBSERVATIONAL_TEACHER_GEOMETRY',time=stamp(),groups=groups,
        early_64_diagnostic=early,quantile_levels=levels,all_P_targets_are_exact_Base_interfaces=True,
        scope='Train and validation metadata only; no model rerun; no test; no configuration change',
        initial_loss_mass_is_not_gradient_mass=True,correlation_is_not_causal_or_a_selection_rule=True))
    atomic(target/'CASE_METADATA.json',values)
    print(json.dumps(dict(event='TEACHER_GEOMETRY_OBSERVATION_COMPLETE',cases=len(values),all_P_targets_exact_Base=True)),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'provenance/TEACHER_GEOMETRY_FAILED_V1.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
