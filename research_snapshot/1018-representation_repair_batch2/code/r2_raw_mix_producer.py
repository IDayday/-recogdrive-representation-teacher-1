"""Prepare an independent raw mixture smoke without changing frozen experiments."""
from r2_common import *
from r2_resume_support import register_once


def main():
    selected=None
    while selected is None:
        for path in (ROOT/'analysis/spatial_proposals').glob('outcome_spatial_proposal_*.json'):
            metadata=read(path);d=read(ROOT/metadata['point'])
            parts=d['arms']
            # The proposal schema is inspected before this controller is registered.
            if not parts:continue
            groups={}
            for p in parts:
                name=p['arm']['block'];area='vision' if name.startswith('vision') else 'language' if name.startswith('language') else 'interface' if name.startswith('interface') else 'other'
                groups.setdefault(area,p)
            if all(k in groups for k in ['vision','language','interface']):selected=(d,[groups[k] for k in ['vision','language','interface']]);break
        if selected is None:time.sleep(30)
    source,parts=selected;stage=ROOT/'runs/raw_multisite_router_smoke_v1'
    held=source['task']['heldout_fold'];panel=source['panel'][:2]
    assert panel
    selection=stage/'selection.json'
    arms=[dict(p,id='raw_smoke_part_'+str(j),slot=j) for j,p in enumerate(parts)]
    bank=dict(system='raw_multisite_engineering_K3_seed0',K=3,heldout_fold=held,arms=arms,policies={role:{str(j):p['id'] for j,p in enumerate(arms)} for role in ['PDMS','safety']})
    if not selection.exists():atomic(selection,bank)
    task=dict(id='raw_multisite_router_smoke_v1',stage=str(stage.relative_to(ROOT)),parts=arms,panel=panel,selection=str(selection.relative_to(ROOT)))
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[task]);atomic(stage/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='raw_multisite_router_real_gradient_and_scoring',path=str(stage.relative_to(ROOT)),handler='code/r2_raw_mix_smoke.py',handler_sha256=sha(ROOT/'code/r2_raw_mix_smoke.py'),kind='custom',priority=7))


if __name__=='__main__':main()
