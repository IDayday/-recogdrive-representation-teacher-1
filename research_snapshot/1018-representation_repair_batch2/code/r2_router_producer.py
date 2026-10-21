"""Queue only complete, fold-contained response-bank routers; pilot first."""
from r2_common import *
from r2_resume_support import append_once


def main():
    folder=ROOT/'analysis/expert_library_selection';queued=set();pilot=None
    while True:
        tasks=[]
        for path in sorted(folder.glob('*.json')):
            selection=read(path);held=selection['heldout_fold'];fold='all' if held<0 else f'fold{held}'
            if not (ROOT/'router_features'/fold/'COMPLETE.json').exists():continue
            responses=[ROOT/'analysis/responses'/name/path.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if not all(p.exists() for p in responses):continue
            for role in ['PDMS','safety']:
                for tier in ['observation','trajectory','denoising']:
                    spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses],role=role,tier=tier)
                    ident='outcome_router_'+digest(spec)[:24]
                    if ident in queued:continue
                    if pilot is None:pilot=ident
                    if ident!=pilot and not (ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json').exists():continue
                    tasks.append(dict(id=ident,handler='code/r2_router_fit.py',handler_sha256=sha(ROOT/'code/r2_router_fit.py'),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        if pilot and (RUN/'receipts_cpu'/(pilot+'.json')).exists() and not (ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json').exists():
            receipt=read(RUN/'receipts_cpu'/(pilot+'.json'));policy=read(ROOT/receipt['result']['path'])
            assert policy['PDMS_GT_not_input_features'] and policy['exact_identity_available']
            atomic(ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json',dict(status='PASS',time=stamp(),pilot=pilot,
                   policy=receipt['result']['path'],rows=policy['rows'],feature_tier=policy['tier'],
                   semantic_policy_rollout_still_required=True,inner_training_result_not_final_cv=True))
        atomic(ROOT/'analysis/routers/PRODUCER.json',dict(time=stamp(),routers_queued=len(queued),pilot=pilot,
               status='QUEUEING_READY_SYSTEMS',pilot_passed=(ROOT/'provenance/ROUTER_FIT_PILOT_PASS.json').exists()))
        # The controller remains available as new systems and refinements finish.
        time.sleep(60)


if __name__=='__main__':main()
