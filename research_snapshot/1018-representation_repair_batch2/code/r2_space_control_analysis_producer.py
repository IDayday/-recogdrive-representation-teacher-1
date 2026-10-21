"""Schedule one complete paired diagnostic reduction, no scientific selection."""
from r2_common import *
from r2_resume_support import append_once


def main():
    stage=ROOT/'runs/space_controllability_v1';queue=stage/'tasks.json'
    while not queue.exists():time.sleep(60)
    tasks=read(queue)
    while True:
        complete=sum((stage/'receipts'/(t['id']+'.json')).exists() for t in tasks)
        atomic(ROOT/'analysis/space_control_summary/PRODUCER.json',dict(time=stamp(),complete=complete,tasks=len(tasks),finite_stage_only=True))
        if complete==len(tasks):break
        time.sleep(60)
    spec=dict(stage=str(stage.relative_to(ROOT)),tasks_sha256=sha(queue));ident='outcome_matched_space_control_'+digest(spec)[:24];handler='code/r2_space_control_analysis.py';append_once('cpu',[dict(id=ident,handler=handler,handler_sha256=sha(ROOT/handler),**spec)])
    atomic(ROOT/'analysis/space_control_summary/SUBMISSION.json',dict(time=stamp(),id=ident,tasks=len(tasks)))


if __name__=='__main__':main()
