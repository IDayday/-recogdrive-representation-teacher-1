"""Use idle DLC CPU workers to prepare exact descriptors ahead of serial supply."""
from r2_common import *
from r2_resume_support import append_once
from collections import defaultdict


def main():
    path=ROOT/'config/CAUSAL_EXPERT_PROTOCOL_V1.json'
    while not path.exists():time.sleep(15)
    tasks=read(path)['fit_tasks'];pilot=next(t for t in tasks if (ROOT/'runs/causal_expert_quick_v1/points'/(t['id']+'.json')).exists())
    append_once('cpu',[dict(id='outcome_causal_descriptor_parallel_pilot',handler='code/r2_causal_point_prepare.py',handler_sha256=sha(ROOT/'code/r2_causal_point_prepare.py'),fits=[pilot],compare_only=True)])
    while not (ROOT/'provenance/CAUSAL_DESCRIPTOR_PARALLEL_EQUIVALENCE.json').exists():time.sleep(15)
    groups=defaultdict(list)
    for t in tasks:groups[(t['responsibility_meta'],t['expert'])].append(t)
    work=[]
    for group,fits in groups.items():
        if all((ROOT/'runs/causal_expert_quick_v1/points'/(t['id']+'.json')).exists() or not read(ROOT/'analysis/delta_experts'/(t['id']+'.json')).get('fits') for t in fits):continue
        work.append(dict(id='outcome_causal_descriptor_'+digest(dict(meta=group[0],expert=group[1]))[:24],handler='code/r2_causal_point_prepare.py',handler_sha256=sha(ROOT/'code/r2_causal_point_prepare.py'),fits=fits,compare_only=False))
    append_once('cpu',work);atomic(ROOT/'provenance/CAUSAL_DESCRIPTOR_PARALLEL_SUBMISSION.json',dict(time=stamp(),tasks=len(work),frozen_rule_unchanged=True,reason='Parallel immutable descriptor creation releases valuable GPU work without waiting for repeated serial population hashing.'))


if __name__=='__main__':main()
