"""Stream two-family and three-family heterogeneous experts from paired banks."""
from r2_common import *
from r2_resume_support import append_once


def main():
    setup('unified_bank_producer');queued=set()
    sources=[dict(name='behavior',folder='expert_library_selection',s0='expert_library_S0_v1',noise='expert_library_noise_v1'),
        dict(name='causal',folder='causal_library_selection',s0='causal_library_S0_v1',noise='causal_library_noise_v1'),
        dict(name='spatial',folder='spatial_library_selection',s0='spatial_library_S0_v1',noise='spatial_library_noise_v1')]
    while True:
        records={}
        for source in sources:
            for path in (ROOT/'analysis'/source['folder']).glob('*.json'):
                d=read(path);pair=[ROOT/'analysis/responses'/name/path.name for name in [source['s0'],source['noise']]]
                if not all(p.exists() for p in pair):continue
                parent=d.get('parent_system',d['system']);key=(d['heldout_fold'],parent);records.setdefault(key,{})[source['name']]=dict(name=source['name'],selection=str(path.relative_to(ROOT)),S0=str(pair[0].relative_to(ROOT)),noise=str(pair[1].relative_to(ROOT)))
        tasks=[]
        for (held,system),ready in records.items():
            for variant,names in [('unified_bc',['behavior','causal']),('unified_bcs',['behavior','causal','spatial'])]:
                if not all(n in ready for n in names):continue
                spec=dict(variant=variant,sources=[ready[n] for n in names]);ident=variant+'_'+digest(dict(held=held,system=system))[:24]
                if ident in queued:continue
                tasks.append(dict(id=ident,handler='code/r2_unified_bank.py',handler_sha256=sha(ROOT/'code/r2_unified_bank.py'),**spec));queued.add(ident)
        if tasks:append_once('cpu',tasks)
        atomic(ROOT/'analysis/unified_banks/PRODUCER.json',dict(time=stamp(),queued=len(queued),known_parent_systems=len(records),no_new_GPU_rollouts_for_bank_composition=True))
        time.sleep(60)


if __name__=='__main__':main()
