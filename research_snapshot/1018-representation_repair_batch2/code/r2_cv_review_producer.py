"""Snapshot completed held policy matrices; no repeated polling by the agent."""
from r2_common import *
from r2_resume_support import append_once


def main():
    previous=set();active=None;stages=['warm_hard_cv_v1','candidate_selector_cv_v1','joint_policy_cv_v1','additional_joint_policy_cv_v1']
    while True:
        paths=[]
        for stage in stages:
            for path in (ROOT/'analysis/responses'/stage).glob('*.json'):
                if read(path)['source_mode']=='heldout':paths.append(str(path.relative_to(ROOT)))
        current=set(paths)
        if current!=previous and current and (active is None or (RUN/'receipts_cpu'/(active+'.json')).exists()):
            spec=dict(responses=sorted(paths),bootstrap_samples=1000);active='outcome_cv_review_'+digest(spec)[:24]
            append_once('cpu',[dict(id=active,handler='code/r2_cv_review.py',handler_sha256=sha(ROOT/'code/r2_cv_review.py'),**spec)]);previous=current
        atomic(ROOT/'analysis/cv_reviews/PRODUCER.json',dict(time=stamp(),held_points_available=len(paths),active_task=active,interval_seconds=120))
        time.sleep(120)


if __name__=='__main__':main()
