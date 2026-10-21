"""Queue a pure CPU reduction after both original fivefold diagnostics exist."""
from r2_common import *
from r2_resume_support import append_once


def main():
    known=set()
    while True:
        stability={};groups={}
        for p in (ROOT/'analysis/held_stability_diagnostics').glob('*.json'):
            d=read(p)
            if d.get('status')=='PRIVILEGED_HELD_DRAW_STABILITY_DIAGNOSTIC':stability[d['source_bank']]=(p,d)
        for p in (ROOT/'analysis/held_bank_potential').glob('*.json'):
            d=read(p)
            if d.get('status')!='HELD_SESSION_PRIVILEGED_DIAGNOSTIC' or d['source_bank'] not in stability:continue
            sp,sd=stability[d['source_bank']];key=d['system'];held=d['heldout_fold'];group=groups.setdefault(key,{})
            if held in group:assert group[held]['potential']==str(p.relative_to(ROOT)),('Duplicate fold identity',key,held)
            group[held]=dict(fold=held,potential=str(p.relative_to(ROOT)),potential_sha256=sha(p),stability=str(sp.relative_to(ROOT)),stability_sha256=sha(sp))
        tasks=[]
        for system,group in groups.items():
            if set(group)!=set(range(5)):continue
            spec=dict(system=system,inputs=[group[j] for j in range(5)]);ident='outcome_held_fivefold_'+digest(spec)[:24]
            if ident in known:continue
            handler='code/r2_held_fivefold_potential.py';tasks.append(dict(id=ident,handler=handler,handler_sha256=sha(ROOT/handler),**spec));known.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/held_fivefold_potential/PRODUCER.json',dict(time=stamp(),queued=len(known),source_systems=len(groups),no_new_GPU_work=True));time.sleep(120)


if __name__=='__main__':main()
