"""Bounded CPU-only dense calibration control; original heavy jobs continue."""
from r2_common import *
from r2_resume_support import append_once


def main():
    setup('gate_breakpoint_producer')
    protocol='config/GATE_BREAKPOINT_CONTROL_PROTOCOL_V1.json';frozen=sha(ROOT/protocol);handler='code/r2_gate_breakpoint_control.py';sourcehash=sha(ROOT/handler)
    assert read(ROOT/'provenance/GATE_BREAKPOINT_ENGINEERING_PASS.json')['source_sha256']==sourcehash
    tasks=[dict(t,protocol=protocol,protocol_sha256=frozen,handler=handler,handler_sha256=sourcehash) for t in read(ROOT/'manifests/GATE_BREAKPOINT_TASKS_FROZEN.json')['tasks']];published=set();firstflag=False
    expected={(f"token_breakpoint_{t['view']}_{v}_wave1",t['system'],t['role']) for t in tasks for v in read(ROOT/protocol)['variants']};assert len(expected)==48
    while True:
        assert sha(ROOT/protocol)==frozen and sha(ROOT/handler)==sourcehash;done={t['id'] for t in tasks if (RUN/'receipts_cpu'/(t['id']+'.json')).exists()};failed=[t['id'] for t in tasks if (RUN/'failures_cpu'/(t['id']+'.json')).exists()]
        if failed:atomic(ROOT/'analysis/gate_breakpoints/ATTENTION.json',dict(time=stamp(),failed_tasks=failed,no_automatic_retry=True));return
        active=published-done;work=[]
        for t in tasks:
            if len(active)+len(work)>=12:break
            if t['id'] in published or t['id'] in done:continue
            work.append(t);published.add(t['id'])
        if work:append_once('cpu',work)
        if len(done)>=8 and not firstflag:
            atomic(ROOT/'analysis/gate_breakpoints/FIRST8_READY.json',dict(time=stamp(),complete_CPU_tasks=len(done),mechanical_only=True));firstflag=True
        pointer=read(ROOT/'analysis/extended_cv_reviews/LATEST.json');review=read(ROOT/pointer['path']);full={(r['method'],r['system'],r['policy']) for r in review['recipes'] if r['complete_five_folds']};complete=expected&full
        atomic(ROOT/'analysis/gate_breakpoints/PRODUCER.json',dict(time=stamp(),published=len(published),completed=len(done),required=len(tasks),complete_fivefold_recipes=len(complete),required_fivefold_recipes=len(expected),no_newGPUtask=True,no_new_model_or_scoring=True))
        if len(done)==len(tasks) and complete==expected:
            atomic(ROOT/'analysis/gate_breakpoints/COMPLETE.json',dict(status='ALL48_PREDECLARED_CALIBRATION_CONTROL_RECIPES_COMPLETE_FIVEFOLD',time=stamp(),snapshot=pointer,completed_CPU_tasks=len(done),recipes=[r for r in review['recipes'] if (r['method'],r['system'],r['policy']) in expected],scope='Fixedexperts/readoutcheckpoint, originalinnercalibration only; allzeroandnegative included. Existingtrajectories/predictions/scores reused. No naturalconfirmation/test.',no_new_model_or_rollout_or_score=True));return
        time.sleep(30)


if __name__=='__main__':main()
