"""Stable paired-gain classification; preserve the fixed teacher and raw v1.

Subtract each paired score before the five-draw sum. A permutation of the same
five scores must not become an improvement because of reduction roundoff.
No epsilon or quality threshold is introduced; real nonzero gains are retained.
"""
from d4_common import *
import math
from collections import Counter


def main():
    old=ROOT/'manifests/R2_SCENES_V1.json';rows=read(old);counts=Counter();changed=[]
    for row in rows:
        before=row['pool'];base=row['Base_scores'];teacher=row['teacher_scores']
        delta=math.fsum(t-b for t,b in zip(teacher,base))/5
        b=math.fsum(base)/5;t=math.fsum(teacher)/5
        assert delta>=0,(row['global_index'],delta)
        pool='I' if delta>0 else 'P' if b>.9 else 'E'
        row.update(Base_mean=b,teacher_mean=t,gain=delta,pool=pool,gain_aggregation='math.fsum of five paired differences / 5')
        counts[row['subset']+'_'+pool]+=1
        if before!=pool:changed.append(dict(index=row['global_index'],before=before,after=pool,paired_gain=delta,Base_scores=base,teacher_scores=teacher))
    path=ROOT/'manifests/R2_TRAINING_SCENES_V2.json';assert not path.exists();atomic(path,rows)
    train=[r['global_index'] for r in rows if r['subset']=='exploration' and r['pool'] in ['I','P']]
    atomic(ROOT/'manifests/TRAIN_INDICES_V2.json',train)
    proof=dict(status='PASS_STABLE_PAIRED_GAIN_CLASSIFICATION',time=stamp(),scenes=len(rows),counts=dict(counts),training_scenes=len(train),
        changed=changed,source_v1_sha256=sha(old),training_scenes_sha256=sha(path),training_indices_sha256=sha(ROOT/'manifests/TRAIN_INDICES_V2.json'),
        threshold_epsilon_used=False,teacher_candidate_or_trajectory_changed=False,raw_v1_preserved=True,
        teacher_replay_still_uses_immutable_v1_identity=True,GT_used=False)
    atomic(ROOT/'provenance/TRAINING_SOURCES_V2.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
