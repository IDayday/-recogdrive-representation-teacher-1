"""Mechanical submission of the no-model matched K2 resampling control."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set()
    while True:
        work=[]
        for path in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
            bank=read(path)
            if bank.get('mode')!='heldout':continue
            spec=dict(bank=str(path.relative_to(ROOT)));ident='outcome_held_stability_'+digest(spec)[:24]
            if ident in queued:continue
            work.append(dict(id=ident,handler='code/r2_held_stability_diagnostic.py',handler_sha256=sha(ROOT/'code/r2_held_stability_diagnostic.py'),**spec));queued.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/held_stability_diagnostics/PRODUCER.json',dict(time=stamp(),banks_queued=len(queued),new_model_runs=0))
        time.sleep(120)


if __name__=='__main__':main()
