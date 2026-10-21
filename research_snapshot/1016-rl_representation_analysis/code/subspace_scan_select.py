"""Complete CV ledger, family correction, stable regions, then immutable hold-out lock."""
from common import *
import numpy as np
from subspace_scan_math import configs,KS,RS
from subspace_scan_prepare import OUT


def bh(p):
    order=np.argsort(p);q=np.empty(len(p));q[order]=np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1].clip(0,1);return q


def neighbors(c,equal):
    i=KS.index(c['ks']);j=KS.index(c['kf']);k=RS.index(c['r']);points=[]
    if equal:
        for delta in [-1,1]:
            if 0<=i+delta<len(KS):points.append((KS[i+delta],KS[i+delta],c['r']))
            if 0<=k+delta<len(RS):points.append((c['ks'],c['kf'],RS[k+delta]))
    else:
        for axis,idx,values in [(0,i,KS),(1,j,KS),(2,k,RS)]:
            for delta in [-1,1]:
                if 0<=idx+delta<len(values):
                    point=[c['ks'],c['kf'],c['r']];point[axis]=values[idx+delta]
                    if point[0]!=point[1]:points.append(tuple(point))
    return points


def eligible(r,route,rule):
    if r['status']!='VALID' or r['cutoff_degenerate_any_fold'] or not r.get('P0'):return False
    a=r['P0'];passes=(a['auc']>=rule['auc_min'] and a['standardized_gap']>=rule['standardized_gap_min'] and r['auc_fold_min']>rule['fold_auc_min'] and a['sessions_with_both_classes']>=rule['min_sessions'] and (a['session_positive_fraction'] or 0)>=rule['session_positive_fraction_min'])
    if route=='r2':
        b=r.get('P1');noise=r.get('noise_consistency',{})
        passes=passes and b is not None and noise.get('common_endpoint_pairs',0)>=rule['route2_min_common_endpoint_pairs'] and min(a.get('pair_ordering',0) or 0,b.get('pair_ordering',0) or 0)>=rule['route2_P0_P1_ordering_min'] and abs((a.get('pair_ordering') or 0)-(b.get('pair_ordering') or 0))<=rule['route2_ordering_gap_max'] and (noise.get('common_branch_order_agreement') or 0)>=rule['route2_common_branch_order_agreement_min']
    return passes


def score(r,route):
    if r['status']!='VALID' or not r.get('P0'):return -.5
    a=r['P0']['auc'];b=r['P1']['auc'] if route=='r2' and r.get('P1') else a
    return min(a,b)-r.get('auc_fold_std',0)


def main(args):
    setup('subspace_scan/select');base=ROOT/'runs'/args.run;assert (base/'CV_DRAINED_RESOURCES_HELD.json').exists()
    assert not (OUT/'FROZEN_CONFIRMATION.json').exists()
    protocol=read(OUT/'PROTOCOL.json');rule=protocol['leader_eligibility'];entries=configs();lookup={(c['ks'],c['kf'],c['r']):i for i,c in enumerate(entries) if c['kind']=='residual'}
    tasks=read(base/'tasks.json');tasks=[t for t in tasks if t['phase']=='cv'];families={'r1':[],'r2':[]};leaders={};cell_index=[];fullledger=[]
    for ci,task in enumerate(tasks):
        path=base/'results'/(task['id']+'.json');proof=read(base/'receipts'/path.name);assert sha(path)==proof['result_sha256'];doc=read(path)
        assert not doc['heldout_validation_evaluated'];route=task['route'];cell=doc['cell'];cell_index.append(dict(cell=cell,task=task,source_sha256=proof['result_sha256']))
        for centering in ['uncentered','pooled_centered']:
            rows=[r for r in doc['search'] if r['centering']==centering];assert len(rows)==673
            by={i:r for i,r in enumerate(rows)};eligible_map={i:eligible(r,route,rule) for i,r in by.items() if r['config']['kind']=='residual'}
            for index,r in by.items():
                c=r['config'];m=r.get('P0');p=m['exploratory_p'] if m and r['status']=='VALID' else 1.
                li=len(fullledger);fullledger.append((ci,0 if centering=='uncentered' else 1,index,int(r['status']=='VALID'),int(r['cutoff_degenerate_any_fold']),p,np.nan,
                    m['auc'] if m else np.nan,m['ap'] if m else np.nan,m['standardized_gap'] if m else np.nan,r['P1']['auc'] if r.get('P1') else np.nan))
                if c['kind']=='residual' and r['status']=='VALID':families[route].append(li)
                if c['kind']!='residual' or r['status']!='VALID' or not m or r['cutoff_degenerate_any_fold']:continue
                near=[lookup[v] for v in neighbors(c,c['equal'])];support=sum(eligible_map.get(v,False) for v in near)
                conservative=float(np.median([score(r,route)]+[score(by[v],route) for v in near]))
                key=(route,centering,c['equal']);entry=dict(cell=cell,cell_index=ci,centering=centering,index=index,cv=r,ledger_index=li,
                    neighbor_indices=near,eligible=eligible_map.get(index,False) and support>=2,eligible_neighbors=support,neighbor_median_conservative_auc=conservative)
                pool=leaders.setdefault(key,[]);pool.append(entry)
                # Bounded top reservoir, effect and neighborhood primary; keep diagnostics if none qualify.
                if len(pool)>400:
                    pool.sort(key=lambda e:(e['eligible'],e['neighbor_median_conservative_auc'],e['cv']['P0']['ap'],e['cv']['P0']['session_positive_fraction'] or 0),reverse=True);del pool[200:]
        if ci%128==0:print(json.dumps(dict(status='CV_LEDGER',cells=ci,total=len(tasks))),flush=True)
    dtype=[('cell','i4'),('center','i1'),('config','i2'),('valid','i1'),('degenerate','i1'),('p','f8'),('q_bh','f8'),('auc_P0','f8'),('ap_P0','f8'),('gap_P0','f8'),('auc_P1','f8')]
    ledger=np.array(fullledger,dtype=dtype);del fullledger
    for route,ii in families.items():
        ii=np.array(ii,dtype=int);ledger['q_bh'][ii]=bh(ledger['p'][ii])
    np.save(OUT/'CV_SEARCH_LEDGER.npy',ledger);atomic(OUT/'CELL_INDEX.json',cell_index)
    regions=[];selected={}
    for key,pool in sorted(leaders.items()):
        pool.sort(key=lambda e:(e['eligible'],e['neighbor_median_conservative_auc'],e['cv']['P0']['ap'],e['cv']['P0']['session_positive_fraction'] or 0),reverse=True)
        chosen=[]
        for entry in pool:
            if chosen and not entry['eligible']:break
            if any(e['cell']==entry['cell'] and (entry['index']==e['index'] or entry['index'] in e['neighbor_indices']) for e in chosen):continue
            chosen.append(entry)
            if len(chosen)>=2 or not entry['eligible']:break
        for entry in chosen:
            rid=f'{key[0]}_{key[1]}_{"equal" if key[2] else "unequal"}_region{len(regions)}';cfg=entries[entry['index']]
            entry['region_id']=rid;entry['q_bh']=float(ledger['q_bh'][entry['ledger_index']]);entry['diagnostic_only']=not entry['eligible']
            regions.append(entry);ids=[entry['index']]+entry['neighbor_indices'];by=selected.setdefault(entry['cell'],{})
            # Only candidates feasible in every fold. No replacement after hold-out evaluation.
            source=read(base/'results'/(cell_index[entry['cell_index']]['task']['id']+'.json'))
            rows=[r for r in source['search'] if r['centering']==entry['centering']]
            ids=[i for i in ids if rows[i]['status']=='VALID']
            rs={entries[i]['r'] for i in ids}
            main_controls=[]
            for r in rs:
                main=next(k for k in KS if k>=r);index=lookup[(main,main,r)]
                if rows[index]['status']=='VALID':main_controls.append(index)
            legacy=lookup[(8,8,8)]
            if rows[legacy]['status']=='VALID':main_controls.append(legacy)
            ids+=main_controls
            ids += [i for i,c in enumerate(entries) if (c['kind']=='random' and c['r'] in rs) or c['kind']=='full']
            for index in ids:
                slot=(entry['centering'],index)
                if slot not in by:by[slot]=dict(centering=entry['centering'],index=index,regions=[],comparison_roles=[],diagnostic_only=entry['diagnostic_only'])
                by[slot]['diagnostic_only']=by[slot]['diagnostic_only'] and entry['diagnostic_only']
                if rid not in by[slot]['regions']:by[slot]['regions'].append(rid)
                role=('leader' if index==entry['index'] else 'neighbor')
                if entries[index]['kind'] in ['random','full']:role=entries[index]['kind']+'_control'
                if index in main_controls:role='main_dimension_matched_r_control' if index!=legacy else 'legacy_k8_r8_anchor'
                if role not in by[slot]['comparison_roles']:by[slot]['comparison_roles'].append(role)
    cells={key:list(value.values()) for key,value in selected.items()};lock=dict(status='FROZEN_BEFORE_HELDOUT_SCORING',time=stamp(),regions=regions,cells=cells,
        cv_search_ledger_sha256=sha(OUT/'CV_SEARCH_LEDGER.npy'),cell_index_sha256=sha(OUT/'CELL_INDEX.json'),protocol_sha256=sha(OUT/'PROTOCOL.json'),
        requested_cells=len(tasks),requested_variants=len(tasks)*1346,bh_families={r:len(v) for r,v in families.items()},validation_result_used_for_selection=False)
    atomic(OUT/'FROZEN_CONFIRMATION.json',lock);frozen_sha=sha(OUT/'FROZEN_CONFIRMATION.json');new=[]
    for cell in cells:
        old=next(r['task'] for r in cell_index if r['cell']==cell);row=dict(old,phase='confirm',selection_sha256=frozen_sha);row['id']='confirm_'+digest(row)[:20];new.append(row)
    assert not set(t['id'] for t in tasks)&set(t['id'] for t in new);atomic(base/'tasks.json',tasks+new)
    atomic(OUT/'SELECTION_COMPLETE.json',dict(status='PASS',time=stamp(),regions=len(regions),cells=len(cells),confirm_tasks=len(new),hypotheses=sum(len(v) for v in cells.values())))
    print(json.dumps(read(OUT/'SELECTION_COMPLETE.json')),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args())
