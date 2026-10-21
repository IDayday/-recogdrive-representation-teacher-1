"""Mechanical potential diagnostics on every completed real response bank."""
from r2_common import *
from r2_resume_support import append_once


def main():
    queued=set()
    while True:
        sources=[dict(folder='expert_library_selection',s0='expert_library_S0_v1',noise='expert_library_noise_v1'),dict(folder='variant_library_selection',s0='variant_library_S0_v1',noise='variant_library_noise_v1'),dict(folder='causal_library_selection',s0='causal_library_S0_v1',noise='causal_library_noise_v1')]+read(ROOT/'config/ADDITIONAL_BANK_SOURCES.json')['sources']
        tasks=[]
        for source in sources:
            for path in (ROOT/'analysis'/source['folder']).glob('*.json'):
                responses=[ROOT/'analysis/responses'/name/path.name for name in [source['s0'],source['noise']]]
                if not all(p.exists() for p in responses):continue
                spec=dict(selection=str(path.relative_to(ROOT)),responses=[str(p.relative_to(ROOT)) for p in responses]);ident='outcome_bank_potential_'+digest(spec)[:24]
                if ident in queued:continue
                tasks.append(dict(id=ident,handler='code/r2_bank_potential.py',handler_sha256=sha(ROOT/'code/r2_bank_potential.py'),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/bank_potential/PRODUCER.json',dict(time=stamp(),banks_queued=len(queued)))
        time.sleep(60)


if __name__=='__main__':main()
