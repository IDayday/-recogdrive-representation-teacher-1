"""Full-coverage bounded-correction diagnostics, separating S0 selection from transfer."""
from r2_common import *


def run(task):
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    indices=[i for i,r in enumerate(rows) if r['subset']=='exploration' and q[i]<.7]
    groups={i:[] for i in indices}
    for path in sorted((ROOT/'analysis/case_corrections').glob('correction_interface_*.json')):
        d=read(path);groups[d['global_index']].append((path,d))
    assert all(len(v)==6 for v in groups.values()),'All six configurations are required'
    configs={};selected=[]
    for index,items in groups.items():
        for path,d in items:
            key=d['block']+'_'+str(d['cap']);records=d['records'];a=records[0]['score'];b=records[d['selected_index']]['score']
            entry=dict(index=index,session=d['session'],base=a['score'],best=b['score'],gain=b['score']-a['score'],
                       repair90=b['score']>.9,repair70=b['score']>=.7,selected=d['selected_index'],
                       edit=records[d['selected_index']]['relative_edit'],gt=records[-1]['score']['score'])
            for j in [1,2]:
                values={r['arm']:r['score'] for r in d['transfer'] if r['seed_index']==j}
                entry['gain_S'+str(j)]=values['selected_on_S0']['score']-values['baseline']['score']
                for component in ['no_at_fault_collisions','drivable_area_compliance','score']:
                    entry['delta_'+component+'_S'+str(j)]=values['selected_on_S0'][component]-values['baseline'][component]
            configs.setdefault(key,[]).append(entry)
        path,d=max(items,key=lambda p:p[1]['records'][p[1]['selected_index']]['score']['score'])
        s=d['records'][d['selected_index']]['score'];a=d['records'][0]['score']
        transfer=[]
        for j in [1,2]:
            values={r['arm']:r['score'] for r in d['transfer'] if r['seed_index']==j}
            transfer.append(dict(seed_index=j,base=values['baseline'],repaired=values['selected_on_S0']))
        selected.append(dict(index=index,token=rows[index]['token'],session=rows[index]['session'],
                     source=str(path.relative_to(ROOT)),base=a,best=s,transfer=transfer))
    summary=[]
    for name,records in configs.items():
        summary.append(dict(configuration=name,cases=len(records),base_pdms=100*np.mean([r['base'] for r in records]),
            selected_S0_pdms=100*np.mean([r['best'] for r in records]),improved=sum(r['gain']>1e-8 for r in records),
            repair90=sum(r['repair90'] for r in records),repair70=sum(r['repair70'] for r in records),
            gains_S1=100*np.mean([r['gain_S1'] for r in records]),gains_S2=100*np.mean([r['gain_S2'] for r in records]),
            transfer_improved_S1=sum(r['gain_S1']>1e-8 for r in records),transfer_damaged_S1=sum(r['gain_S1']< -1e-8 for r in records),
            GT90=sum(r['gt']>.9 for r in records)))
    result=dict(status='COMPLETE',time=stamp(),cases=len(indices),case_configurations=sum(map(len,groups.values())),
                configurations=summary,best_configuration_on_S0=selected,per_configuration=configs,
                privileged=True,deployable_gain_claim=False,
                interpretation='Per-scene bounded gradient optimization with GT and real S0 selection; transfer repeats the same chosen edit on S1/S2.',
                final_validation=False,test_accessed=False)
    path=ROOT/'analysis/correction_diagnostics/SUMMARY.json';atomic(path,result)
    return dict(path=str(path.relative_to(ROOT)),cases=len(indices),configuration_summary=summary)
