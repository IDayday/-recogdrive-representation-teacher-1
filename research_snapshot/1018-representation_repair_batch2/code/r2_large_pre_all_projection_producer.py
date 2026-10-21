"""Include the second predeclared large-success view in canonical CV statistics.

Original producer projects post_valid. This fills only pre_all; no prediction,
policy selection or scoring changes and no duplicate post_valid projections.
"""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set()
    while True:
        work=[]
        for p in (ROOT/'analysis/context_token_policy_cv/pre_all').glob('largeH_held_*.json'):
            d=read(p);assert d['context_view']=='pre_all' and d['heldout_fold']==0 and '__largeH_' in d['system']
            ident=p.stem.removeprefix('largeH_held_');ident='outcome_largeH_projection_'+ident
            if ident in queued:continue
            work.append(dict(id=ident,handler='code/r2_context_cv_projection.py',handler_sha256=sha(ROOT/'code/r2_context_cv_projection.py'),assessment=str(p.relative_to(ROOT)),context_control='large_success_pre_all'));queued.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/large_success_critic_control/PRE_ALL_PROJECTION.json',dict(time=stamp(),queued=len(queued),CPU_only=True,no_new_trajectories_or_selection=True));time.sleep(120)


if __name__=='__main__':main()
