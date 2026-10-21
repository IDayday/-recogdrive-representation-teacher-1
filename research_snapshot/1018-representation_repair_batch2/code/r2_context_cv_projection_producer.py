"""Expose context-view held results to the existing comprehensive review."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set()
    while True:
        work=[]
        for view in ['pre_valid','post_all','pre_all']:
            for path in (ROOT/'analysis/context_token_policy_cv'/view).glob('*.json'):
                d=read(path)
                if d.get('status')!='HELDOUT_POLICY_EVALUATED':continue
                spec=dict(assessment=str(path.relative_to(ROOT)),context_control='context_'+view);ident='outcome_context_cv_projection_'+digest(spec)[:24]
                if ident in queued:continue
                work.append(dict(id=ident,handler='code/r2_context_cv_projection.py',handler_sha256=sha(ROOT/'code/r2_context_cv_projection.py'),**spec));queued.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/context_cv_projection/PRODUCER.json',dict(time=stamp(),tasks=len(queued)))
        time.sleep(120)


if __name__=='__main__':main()
