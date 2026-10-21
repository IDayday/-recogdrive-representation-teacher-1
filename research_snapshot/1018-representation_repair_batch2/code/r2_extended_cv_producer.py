"""Full-token and pooled controls join the same held-session statistical review."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set();previous=set();active=None
    while True:
        work=[]
        for folder,kind in [('token_policy_cv','full'),('uniform_token_policy_cv','uniform')]:
            for path in (ROOT/'analysis'/folder).glob('*.json'):
                d=read(path)
                if d.get('status')!='HELDOUT_POLICY_EVALUATED':continue
                spec=dict(assessment=str(path.relative_to(ROOT)),context_control=kind);ident='outcome_token_cv_projection_'+digest(spec)[:24]
                if ident not in queued:work.append(dict(id=ident,handler='code/r2_token_cv_projection.py',handler_sha256=sha(ROOT/'code/r2_token_cv_projection.py'),**spec));queued.add(ident)
        if work:append_once('cpu',work)
        paths=[]
        for folder in ['warm_hard_cv_v1','candidate_selector_cv_v1','joint_policy_cv_v1','additional_joint_policy_cv_v1','token_full_cv_projection_v1','token_uniform_cv_projection_v1']:
            for path in (ROOT/'analysis/responses'/folder).glob('*.json'):
                if read(path).get('source_mode')=='heldout':paths.append(str(path.relative_to(ROOT)))
        current=set(paths)
        if current!=previous and current and (active is None or (RUN/'receipts_cpu'/(active+'.json')).exists()):
            spec=dict(responses=sorted(paths),bootstrap_samples=1000);active='outcome_extended_cv_review_'+digest(spec)[:24]
            append_once('cpu',[dict(id=active,handler='code/r2_extended_cv_review.py',handler_sha256=sha(ROOT/'code/r2_extended_cv_review.py'),**spec)]);previous=current
        atomic(ROOT/'analysis/extended_cv_reviews/PRODUCER.json',dict(time=stamp(),projection_tasks_queued=len(queued),held_points_available=len(paths),active_task=active))
        time.sleep(120)


if __name__=='__main__':main()
