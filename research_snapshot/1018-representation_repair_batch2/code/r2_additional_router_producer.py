"""Extensible independent bank sources, same verified hard/candidate learners."""
from r2_common import *
from r2_resume_support import append_once


def main():
    setup('additional_router_producer');queued=set()
    while True:
        tasks=[]
        for source in read(ROOT/'config/ADDITIONAL_BANK_SOURCES.json')['sources']:
            for path in (ROOT/'analysis'/source['folder']).glob('*.json'):
                responses=[ROOT/'analysis/responses'/name/path.name for name in [source['s0'],source['noise']]]
                if not all(p.exists() for p in responses):continue
                for kind,handler,tiers in [('hard','code/r2_router_fit.py',['observation','trajectory','denoising']),('selector','code/r2_candidate_selector.py',['trajectory','denoising'])]:
                    for role in ['PDMS','safety']:
                        for tier in tiers:
                            spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses],role=role,tier=tier)
                            ident='outcome_additional_'+kind+'_'+digest(spec)[:24]
                            if ident in queued:continue
                            tasks.append(dict(id=ident,handler=handler,handler_sha256=sha(ROOT/handler),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/additional_routers/PRODUCER.json',dict(time=stamp(),fits_queued=len(queued),source_registry='config/ADDITIONAL_BANK_SOURCES.json'))
        time.sleep(60)


if __name__=='__main__':main()
