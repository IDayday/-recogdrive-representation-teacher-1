"""Freeze CV-specific location search, without reusing global label-ranked sites."""
from r2_common import *
from collections import defaultdict
from r2_select_locations import component


def main():
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    handler='code/r2_expert_space.py';version=sha(ROOT/handler);tasks=[];selections=[]
    for held in range(5):
        records=defaultdict(list)
        for cell in cells:
            result=read(ROOT/'analysis/fold_proposals'/f'fold{held}'/(cell+'.json'))
            if result['status']!='COMPLETE':continue
            for r in result['experts']:
                if r['ess']>=24 and r['dominant_sessions']>=4:records[(r['system'],r['expert'])].append(r)
        selected={}
        def keep(r,reason):
            key=(r['system'],r['expert'],r['source_cell'])
            selected.setdefault(key,dict(r,reasons=[]))['reasons'].append(reason)
        for key,options in records.items():
            for area in ['vision','bridge','language','interface']:
                pool=[r for r in options if component(cells[r['source_cell']]['block'])==area]
                pool.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
                for r in pool[:2]:keep(r,'fold-only component proposal')
            pool=sorted(options,key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
            for r in pool[:2]:keep(r,'fold-only global proposal')
        systems=read(ROOT/'analysis/initial_groups'/f'fold{held}'/'COMPLETE.json')['initialization_systems']
        blocks=sorted({c['block'] for c in cells.values()})
        for system in systems:
            for j,block in enumerate(blocks):
                expert=j%system['K'];pool=[r for r in records[(system['id'],expert)] if cells[r['source_cell']]['block']==block]
                pool.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
                if pool:keep(pool[0],'all-layer coverage within training fold')
        for r in sorted(selected.values(),key=lambda r:(component(cells[r['source_cell']]['block'])!='interface',r['system'],r['expert'],r['source_cell'])):
            selections.append(r)
            for centered in [False,True]:
                spec=dict(cell=cells[r['source_cell']],expert=r['expert'],heldout_fold=held,centered=centered,
                          responsibility_meta=f'analysis/initial_groups/fold{held}/'+r['system']+'.json')
                tasks.append(dict(id='space_cv_'+digest(spec)[:20],handler=handler,handler_sha256=version,**spec))
    result=dict(status='FROZEN',time=stamp(),tasks=tasks,selected_locations=selections,folds=5,
                all_label_dependent_selection_excludes_heldfold=True,
                global_exploration_proposals_not_reused=True,validation_fitted=False,test_accessed=False)
    atomic(ROOT/'config/FOLD_LOCATION_PROTOCOL.json',result);append('cpu',tasks)
    print(json.dumps(dict(status='SUBMITTED',space_fit_tasks=len(tasks),selected_locations=len(selections))))


if __name__=='__main__':main()
