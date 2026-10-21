"""Explicit algebra for unresolved pools and repeatable marginal improvement.

R3 calls these functions with the first three draws only. Full five-draw
admission is never reused as R3 admission for newly searched configurations.
"""


def unresolved(scores):
    import numpy as np
    q=np.asarray(scores,dtype=np.float64)
    assert q.ndim==3 and np.isfinite(q).all() and q.shape[2] in [3,5]
    u1=(q.max(1)<.9).any(1)
    u2=q.mean(2).max(1)<.9
    return dict(U1=u1,U2=u2,union=u1|u2)


def incremental_gain(existing,candidate):
    import numpy as np
    q=np.asarray(existing,dtype=np.float64);x=np.asarray(candidate,dtype=np.float64)
    assert q.ndim==3 and x.shape==(q.shape[0],q.shape[2]) and np.isfinite(q).all() and np.isfinite(x).all()
    current1=q.max(1);current2=q.mean(2).max(1)
    return dict(R1=(np.maximum(current1,x)-current1).mean(1),R2=np.maximum(current2,x.mean(1))-current2)


def repeated_improvement(existing,repeated_candidate_scores):
    import numpy as np
    assert len(repeated_candidate_scores)>=2,'One execution alone is not repeatability evidence'
    values=[incremental_gain(existing,x) for x in repeated_candidate_scores]
    r1=np.min(np.stack([v['R1'] for v in values]),axis=0)>0
    r2=np.min(np.stack([v['R2'] for v in values]),axis=0)>0
    return dict(R1_cases=r1,R2_cases=r2,eligible_cases=r1|r2,eligible=bool((r1|r2).any()),repetitions=len(values))
