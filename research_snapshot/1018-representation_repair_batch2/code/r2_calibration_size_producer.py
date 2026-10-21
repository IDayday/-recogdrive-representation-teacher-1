from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set()
    while True:
        work=[]
        for view in ['post_valid','pre_all']:
            for p in (ROOT/'analysis/context_token_policy_cv'/view).glob('largeH_held_*.json'):
                d=read(p)
                if '__largeH_frozen8k_' not in d.get('system',''):continue
                spec=dict(assessment=str(p.relative_to(ROOT)));ident='outcome_calibration_size_'+digest(spec)[:24]
                if ident in queued:continue
                work.append(dict(id=ident,handler='code/r2_calibration_size_control.py',handler_sha256=sha(ROOT/'code/r2_calibration_size_control.py'),**spec));queued.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/calibration_size_control/PRODUCER.json',dict(time=stamp(),queued=len(queued)));time.sleep(120)


if __name__=='__main__':main()
