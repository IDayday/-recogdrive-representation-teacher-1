"""Reuse verified response-supervised router families on the new EM bank."""
from r2_common import *
from r2_resume_support import append_once


def main():
    setup('variant_router_producer');queued=set()
    while True:
        tasks=[]
        for path in (ROOT/'analysis/causal_library_selection').glob('*.json'):
            responses=[ROOT/'analysis/responses'/name/path.name for name in ['causal_library_S0_v1','causal_library_noise_v1']]
            if not all(p.exists() for p in responses):continue
            for kind,handler,tiers in [('hard','code/r2_router_fit.py',['observation','trajectory','denoising']),('selector','code/r2_candidate_selector.py',['trajectory','denoising'])]:
                for role in ['PDMS','safety']:
                    for tier in tiers:
                        spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses],role=role,tier=tier)
                        ident='outcome_causal_'+kind+'_'+digest(spec)[:24]
                        if ident in queued:continue
                        tasks.append(dict(id=ident,handler=handler,handler_sha256=sha(ROOT/handler),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/causal_routers/PRODUCER.json',dict(time=stamp(),fits_queued=len(queued),
            heldout_policy_rollouts='Existing whole-policy producers discover new policy artifacts; exact original fold guards remain active.'))
        time.sleep(60)


if __name__=='__main__':main()
