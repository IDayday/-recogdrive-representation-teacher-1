"""Freeze an early all-component intervention wave from training-fold proposals.

One location per component per expert is only a functional proposal. The already
running all-layer sweeps remain intact; actual outcomes, not AUROC, select experts.
"""
from r2_common import *


def run(task):
    from r2_select_locations import component
    configs=[ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json',ROOT/'config/FOLD_LOCATION_PROTOCOL.json']+sorted((ROOT/'config/family_locations').glob('*.json'))
    assert len(configs)==14
    entries=[];sources=[]
    for path in configs:
        d=read(path);lookup={}
        for t in d['tasks']:
            if t['centered']:lookup[(t['responsibility_meta'],t['expert'],t['cell']['cell'])]=t
        selected={}
        for r in d['selected_locations']:
            meta=str(Path(r['responsibility_path']).with_suffix('.json'));t=lookup[(meta,r['expert'],r['source_cell'])]
            held=t['heldout_fold'];key=(held,r['system'],r['expert'],component(t['cell']['block']))
            if key not in selected or (r['training_auc'],r['training_standardized_gap'])>(selected[key][0]['training_auc'],selected[key][0]['training_standardized_gap']):selected[key]=(r,t)
        for key,(r,t) in selected.items():
            held,system,expert,area=key;global_repr=held<0 and system.startswith('representation_')
            entries.append(dict(id=t['id'],task=t,system=system,K=r['K'],fit_seed=r['fit_seed'],heldout_fold=held,expert=expert,area=area,
                source_protocol=str(path.relative_to(ROOT)),source_proposal=r,
                response_stage='spatial_discovery_global_v1' if global_repr else 'fold_and_outcome_probes_v1',global_repr=global_repr))
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),entries=len(selected)))
    entries.sort(key=lambda e:(not(e['heldout_fold']>=0 and e['fit_seed']==2026101801 and e['K'] in [2,3,4]),e['heldout_fold'],e['K'],e['system'],e['expert'],e['area']))
    path=ROOT/'config/SPATIAL_DISCOVERY_WAVE1.json';atomic(path,dict(status='FROZEN_TRAINING_PROPOSALS',time=stamp(),entries=entries,sources=sources,
        location_rule='Highest training-fold descriptor within each of vision/bridge/language/interface, common-centered. This only proposes candidates; actual score is required.',
        global_panel='3 own failures,2 other failures,2 high,1 intermediate; 2 representative spaces and30 operator/strength proposals.',
        remaining_search='All previously frozen layer/token/rank/operator sweeps remain running. No conclusion of exhaustive search.',
        fit_replicates='Screen predefined seed0 for all K/families/folds; admit remaining replicas for retained recipes before independent validation.',
        no_global_classification_claim=True,validation_fitted=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)),entries=len(entries),components=['vision','bridge','language','interface'])
