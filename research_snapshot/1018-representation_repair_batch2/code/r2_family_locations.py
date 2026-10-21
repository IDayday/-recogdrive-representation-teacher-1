"""Select outcome-family sites independently inside each fit fold as it completes."""
from r2_common import *
from collections import defaultdict
from r2_select_locations import component


def main():
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    completed=set();handler='code/r2_expert_space.py';version=sha(ROOT/handler)
    while len(completed)<12:
        for held in [-1,0,1,2,3,4]:
            fold_name='all' if held<0 else f'fold{held}'
            for family in ['response','correction']:
                key=(family,held)
                if key in completed:continue
                folder=ROOT/'analysis/family_proposals'/family/fold_name
                if len(list(folder.glob('*.json')))<len(cells):continue
                record=defaultdict(list)
                for cell in cells:
                    result=read(folder/(cell+'.json'))
                    if result['status']!='COMPLETE':continue
                    for r in result['experts']:
                        if r['ess']>=24 and r['dominant_sessions']>=4:record[(r['system'],r['expert'])].append(r)
                selected={}
                def keep(r,reason):
                    unique=(r['system'],r['expert'],r['source_cell'])
                    selected.setdefault(unique,dict(r,reasons=[]))['reasons'].append(reason)
                for unique,items in record.items():
                    for area in ['vision','bridge','language','interface']:
                        options=[r for r in items if component(cells[r['source_cell']]['block'])==area]
                        options.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
                        for r in options[:2]:keep(r,'subgroup-specific component proposal')
                    for r in sorted(items,key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)[:2]:keep(r,'subgroup-specific global proposal')
                meta_folder=ROOT/'analysis/outcome_groups'/fold_name
                systems=read(meta_folder/(family+'_COMPLETE.json'))['initialization_systems']
                for system in systems:
                    for j,block in enumerate(sorted({c['block'] for c in cells.values()})):
                        expert=j%system['K'];pool=[r for r in record[(system['id'],expert)] if cells[r['source_cell']]['block']==block]
                        pool.sort(key=lambda r:(r['training_auc'],r['training_standardized_gap']),reverse=True)
                        if pool:keep(pool[0],'all-layer coverage, training-fold-only rotating search allocation')
                tasks=[]
                for r in sorted(selected.values(),key=lambda r:(component(cells[r['source_cell']]['block'])!='interface',r['system'],r['expert'],r['source_cell'])):
                    for centered in [False,True]:
                        spec=dict(cell=cells[r['source_cell']],expert=r['expert'],heldout_fold=held,centered=centered,
                                  responsibility_meta=str((meta_folder/(r['system']+'.json')).relative_to(ROOT)))
                        tasks.append(dict(id='family_space_'+digest(spec)[:20],handler=handler,handler_sha256=version,**spec))
                target=ROOT/'config/family_locations'/(family+'_'+fold_name+'.json')
                assert not target.exists()
                atomic(target,dict(status='FROZEN',time=stamp(),family=family,heldout_fold=held,
                       selected_locations=list(selected.values()),tasks=tasks,all_layers_preserved=True,
                       all_label_dependent_fits_exclude_heldfold=True,validation_fitted=False,test_accessed=False))
                append('cpu',tasks);completed.add(key)
                print(json.dumps(dict(status='SECTION_SUBMITTED',family=family,heldout_fold=held,tasks=len(tasks))),flush=True)
        if len(completed)<12:time.sleep(60)
    print(json.dumps(dict(status='ALL_SECTIONS_SUBMITTED',sections=len(completed))),flush=True)


if __name__=='__main__':main()
