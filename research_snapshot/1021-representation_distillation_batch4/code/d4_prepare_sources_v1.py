"""Read first42 R2 only, preserve splits, and classify strict unrounded gains."""
from d4_common import *
from collections import Counter


def main():
    import numpy as np
    frozen_path=B3/'teachers/first42_v1/FROZEN.json';frozen=read(frozen_path)
    assert frozen['status']=='FROZEN_FIRST42_TEACHER_SNAPSHOT' and not frozen['test_targets_included_for_student_training']
    teacher_path=B3/frozen['artifacts']['R2']['path'];assert sha(teacher_path)==frozen['artifacts']['R2']['sha256']
    summary_path=B3/frozen['train_summary'];assert sha(summary_path)==frozen['train_summary_sha256']
    summary=read(summary_path);assert summary['cases']==103288 and summary['status']=='PASS_COMPLETE_AUDITED_FIRST42'
    rows=read(summary['rows']);assert sha(summary['rows'])==summary['rows_sha256']
    pack_path=B3/'teachers/first42_v1/PACK.json';pack=read(pack_path);assert sha(pack_path)==frozen['pack_sha256']
    ids=[e['id'] for e in pack['entries']];q=np.load(B3/summary['artifacts']['scores.npy']['path'],mmap_mode='r')
    selected=np.load(B3/summary['artifacts']['selected.npy']['path'],mmap_mode='r')
    scenes=[];counts=Counter();gains=[]
    with teacher_path.open() as stream:
        for line in stream:
            ref=json.loads(line);i=ref['global_index'];row=rows[i]
            assert i==len(scenes) and ref['token']==row['token'] and ref['subset']==row['subset']
            chosen=int(selected[i,5]);ident=ids[chosen];assert ref['candidate_ids_by_noise']==[ident]*5
            base=q[i,0,:,0];teacher=q[i,chosen,:,0]
            b=float(base.mean());t=float(teacher.mean());delta=t-b;assert delta>=0
            pool='I' if delta>0 else 'P' if b>.9 else 'E'
            counts[row['subset']+'_'+pool]+=1
            if delta>0:gains.append(delta)
            scenes.append(dict(row,global_index=i,teacher_candidate=ident,pool=pool,Base_mean=b,teacher_mean=t,gain=delta,
                Base_scores=base.tolist(),teacher_scores=teacher.tolist(),Base_any_below70=bool((base<.7).any()),
                source_record=ref['record'],source_record_sha256=ref['record_sha256'],source_interfaces=ref['interfaces'],source_interfaces_sha256=ref['interfaces_sha256']))
    assert len(scenes)==103288
    path=ROOT/'manifests/R2_SCENES_V1.json';assert not path.exists();atomic(path,scenes)
    train=[s['global_index'] for s in scenes if s['subset']=='exploration' and s['pool'] in ['I','P']]
    valid=[s['global_index'] for s in scenes if s['subset']=='validation']
    atomic(ROOT/'manifests/TRAIN_INDICES_V1.json',train);atomic(ROOT/'manifests/VALIDATION_INDICES_V1.json',valid)
    smoke=[]
    for subset,pool,hard in [('exploration','I',True),('exploration','I',False),('exploration','P',False),('validation','I',True)]:
        choices=[s for s in scenes if s['subset']==subset and s['pool']==pool and (not hard or s['Base_any_below70'])]
        choice=max(choices,key=lambda s:(s['gain'],-s['global_index'])) if pool=='I' else choices[0]
        if choice['global_index'] not in smoke:smoke.append(choice['global_index'])
    atomic(ROOT/'manifests/SMOKE_INDICES_V1.json',smoke)
    proof=dict(status='PASS_FROZEN_R2_SOURCE_CLASSIFICATION',time=stamp(),scenes=len(scenes),counts=dict(counts),training_scenes=len(train),validation_scenes=len(valid),
        frozen_snapshot_sha256=sha(frozen_path),teacher_R2_sha256=sha(teacher_path),scene_manifest_sha256=sha(path),
        pack_sha256=sha(pack_path),checkpoint_sha256=pack['checkpoint_sha256'],smoke_indices=smoke,
        positive_gain_quantiles=np.quantile(gains,[0,.25,.5,.75,.9,.99,1]).tolist(),GT_used=False,
        test_used_for_training_or_selection=False,training_subset='exploration_only',teacher_candidates_not_reselected=True)
    atomic(ROOT/'provenance/SOURCE_INTAKE_V1.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
