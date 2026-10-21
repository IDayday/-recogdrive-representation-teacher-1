"""Freeze broad expert-specific locations, retaining all 62 blocks per system."""
from r2_common import *
import collections


def component(block):
    return 'vision' if block.startswith('vision') else 'bridge' if block.startswith('bridge') else 'interface' if block.startswith('interface') else 'language'


def main():
    setup('select_locations')
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    records=collections.defaultdict(list)
    for name in sorted(cells):
        p=ROOT/'analysis/group_proposals'/(name+'.json')
        assert p.exists(),name
        result=read(p)
        if result['status']!='COMPLETE':continue
        for record in result['experts']:
            if record['ess']<24 or record['dominant_sessions']<4:continue
            records[(record['system'],record['expert'])].append(record)
    selected={}
    def keep(record,reason):
        key=(record['system'],record['expert'],record['source_cell'])
        selected.setdefault(key,dict(record,reasons=[]))['reasons'].append(reason)
    for key,items in records.items():
        for area in ['vision','bridge','language','interface']:
            options=[r for r in items if component(cells[r['source_cell']]['block'])==area]
            options.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
            for r in options[:2]:keep(r,'per-expert component representative')
        options=sorted(items,key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
        for r in options[:2]:keep(r,'per-expert global proposal')
    # This is search allocation, not a router load-balancing requirement. Each
    # system gets real intervention coverage at every backbone/interface block.
    systems=read(ROOT/'analysis/initial_groups/all/COMPLETE.json')['initialization_systems']
    blocks=sorted({c['block'] for c in cells.values()})
    for system in systems:
        for j,block in enumerate(blocks):
            expert=j%system['K']
            options=[r for r in records[(system['id'],expert)] if cells[r['source_cell']]['block']==block]
            options.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
            if options:keep(options[0],'all-layer coverage, rotating expert search allocation')
    tasks=[];handler='code/r2_expert_space.py';code=sha(ROOT/handler)
    ordered=sorted(selected.values(),key=lambda r:(component(cells[r['source_cell']]['block'])!='interface',
                                                   r['system'],r['expert'],r['source_cell']))
    for record in ordered:
        for centered in [False,True]:
            spec=dict(cell=cells[record['source_cell']],expert=record['expert'],heldout_fold=-1,
                      centered=centered,responsibility_meta='analysis/initial_groups/all/'+record['system']+'.json')
            ident='space_repr_'+digest(spec)[:20]
            tasks.append(dict(id=ident,handler=handler,handler_sha256=code,**spec))
    protocol=dict(status='FROZEN',time=stamp(),initialization_family='representation_multiview',
                  systems=len(systems),nonzero_experts=sum(s['K'] for s in systems),
                  searched_cells=len(cells),selected_expert_locations=len(selected),space_fit_tasks=len(tasks),
                  selected_locations=ordered,tasks=tasks,
                  selection='Training descriptors propose candidates; later actual intervention/CV decides retention.',
                  all_layers_preserved_per_system=True,test_accessed=False,validation_accessed=False)
    atomic(ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json',protocol)
    append('cpu',tasks)
    print(json.dumps({k:protocol[k] for k in ['systems','nonzero_experts','searched_cells','selected_expert_locations','space_fit_tasks']}))


if __name__=='__main__':main()
