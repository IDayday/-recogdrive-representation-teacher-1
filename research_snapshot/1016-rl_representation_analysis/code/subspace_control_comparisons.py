"""Paired same-session comparisons of frozen readouts; maxT simultaneous intervals."""
from common import *
import numpy as np
from threadpoolctl import threadpool_limits
from subspace_scan_prepare import OUT
from subspace_scan_cv import mul,endpoint
from subspace_scan_math import metrics


def weighted_metrics(v,y,inv,draws):
    order=np.argsort(-v,kind='stable');s=v[order];ys=y[order];ends=np.r_[np.flatnonzero(np.diff(s)!=0),len(s)-1];values=[]
    for at in range(0,len(draws),25):
        w=draws[at:at+25,inv[order]];tp=np.cumsum(w*ys,axis=1)[:,ends];total=np.cumsum(w,axis=1)[:,ends];fp=total-tp
        auc=np.sum(np.diff(np.c_[np.zeros(len(w)),fp],axis=1)*(tp+np.c_[np.zeros(len(w)),tp[:,:-1]])*.5,axis=1)/np.maximum(tp[:,-1]*fp[:,-1],1)
        ap=np.sum(np.diff(np.c_[np.zeros(len(w)),tp],axis=1)/np.maximum(tp[:,-1,None],1)*tp/np.maximum(total,1),axis=1)
        out=np.stack([auc,ap],1);out[(tp[:,-1]==0)|(fp[:,-1]==0)]=np.nan;values.append(out)
    return np.concatenate(values)


def main():
    setup('subspace_scan/control_comparisons');protocol=read(OUT/'CONTROL_COMPARISON_PROTOCOL.json');doc=read(OUT/'CONFIRMATION_RESULTS.json');assert read(OUT/'FINAL_ACCEPTANCE.json')['status']=='PASS'
    cfg=read(ROOT/'configs/subspace_scan_execution_v2.json');records=doc['records'];cache={};draws={};universes={}
    for route,file in [('r1','natural_metadata.json'),('r2','paired_metadata.json')]:
        meta=read(OUT/file);sessions=sorted({r['session'] for r in meta if r['subset']=='validation'});universes[route]=sessions
        rng=np.random.default_rng(20261016);draws[route]=rng.multinomial(len(sessions),np.full(len(sessions),1/len(sessions)),size=500)
    with threadpool_limits(limits=4):
        for cell in sorted({r['cell'] for r in records}):
            rr=[r for r in records if r['cell']==cell];route=rr[0]['route'];task=rr[0]['task'];meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'));valid=np.array([r['subset']=='validation' for r in meta]);sessions=np.array([r['session'] for r in meta]);x=np.load(OUT/'cache'/(cell+'.npy'),mmap_mode='r');universe={s:i for i,s in enumerate(universes[route])}
            q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy') if route=='r1' else np.load(OUT/f'cache/r2_a{task["start"]}_scores.npy')
            for centering in ['uncentered','pooled_centered']:
                group=[r for r in rr if r['centering']==centering and (r.get('P0') or r.get('P1'))]
                if not group:continue
                fit=group[0]['fit'];assert all(r['fit']==fit for r in group)
                with np.load(ROOT/fit['path'],allow_pickle=False) as z:w=np.array(z['weights']);center=z['midpoint'];indices=z['indices'].tolist()
                for g in ([0] if route=='r1' else [0,1]):
                    field=f'P{g}';mask=valid&(((q<.7)|(q>.9)) if route=='r1' else endpoint(q[g]))
                    if not mask.any():continue
                    a=np.asarray(x[mask]) if route=='r1' else np.asarray(x[g,mask]).reshape(-1,x.shape[-1]);labels=q[mask]<.7 if route=='r1' else q[g,mask].reshape(-1)<.7
                    ss=sessions[mask] if route=='r1' else np.repeat(sessions[mask],2);inv=np.array([universe[s] for s in ss]);pred=mul(a,w,center,cfg['score_backend'])
                    checked=metrics(pred,labels,ss)
                    for r in group:
                        if not r.get(field):continue
                        j=indices.index(r['index']);m=checked[j]
                        assert abs(m['auc']-r[field]['auc'])<1e-9 and abs(m['ap']-r[field]['ap'])<1e-9,(cell,r['index'],field)
                        boot=weighted_metrics(pred[:,j],labels,inv,draws[route]);cache[(cell,centering,r['index'],field)]=dict(point=np.array([m['auc'],m['ap']]),boot=boot)
            print(json.dumps(dict(status='CONTROL_BOOTSTRAP_CELL',cell=cell,cached_readouts=len(cache))),flush=True)
    contrasts=[];unavailable=[]
    for region in doc['regions']:
        leader=region['leader'];cell=region['cell'];centering=region['centering'];route=region['route'];r=leader['config']['r'];rr=[v for v in records if v['cell']==cell and v['centering']==centering]
        randoms=[v for v in rr if v['config']['kind']=='random' and v['config']['r']==r];full=[v for v in rr if v['config']['kind']=='full'];main=sorted([v for v in rr if v['config']['kind']=='residual' and v['config']['ks']==v['config']['kf'] and v['config']['r']==r],key=lambda v:v['config']['ks'])[:1]
        references=[('same_r_random_mean',randoms),('full_dimension',full),('minimum_equal_main_same_r',main)]
        for field in (['P0'] if route=='r1' else ['P0','P1']):
            lk=(cell,centering,leader['index'],field)
            if lk not in cache:
                unavailable.append(dict(region_id=region['region_id'],route=route,noise=field,status='LEADER_UNAVAILABLE'));continue
            for label,refs in references:
                if not refs or (label=='same_r_random_mean' and len(refs)!=3):
                    unavailable.append(dict(region_id=region['region_id'],route=route,noise=field,control=label,status='FROZEN_REFERENCE_UNAVAILABLE'));continue
                keys=[(cell,centering,v['index'],field) for v in refs]
                if any(k not in cache for k in keys):
                    unavailable.append(dict(region_id=region['region_id'],route=route,noise=field,control=label,status='REFERENCE_METRICS_UNAVAILABLE'));continue
                ref_point=np.mean([cache[k]['point'] for k in keys],0);ref_boot=np.mean([cache[k]['boot'] for k in keys],0)
                for j,metric in enumerate(['AUROC','AP']):
                    point=float(cache[lk]['point'][j]-ref_point[j]);boot=cache[lk]['boot'][:,j]-ref_boot[:,j]
                    contrasts.append(dict(region_id=region['region_id'],route=route,cell=cell,centering=centering,noise=field,metric=metric,
                        control=label,reference_indices=[v['index'] for v in refs],estimate=point,bootstrap=boot))
    output=[];families={}
    for route in ['r1','r2']:
        group=[r for r in contrasts if r['route']==route]
        if not group:families[route]=dict(contrasts=0);continue
        arrays=np.stack([r['bootstrap'] for r in group],1);finite=np.isfinite(arrays).all(1);values=arrays[finite];assert len(values)>=400,(route,'Too many empty-cohort resamples')
        points=np.array([r['estimate'] for r in group]);se=values.std(0,ddof=1);standard=np.abs(values-points)/np.maximum(se,1e-15);critical=float(np.quantile(np.max(standard,axis=1),.95));families[route]=dict(contrasts=len(group),valid_common_bootstrap_draws=len(values),maxT_critical=critical)
        for j,r in enumerate(group):
            item={k:v for k,v in r.items() if k!='bootstrap'};width=critical*se[j]
            item.update(simultaneous_ci95=[float(points[j]-width),float(points[j]+width)],bootstrap_standard_error=float(se[j]),family=route,method='centered session bootstrap maxT approximate simultaneous interval')
            output.append(item)
    atomic(OUT/'CONTROL_COMPARISONS.json',dict(status='COMPLETE',time=stamp(),protocol_sha256=sha(OUT/'CONTROL_COMPARISON_PROTOCOL.json'),code_sha256=sha(Path(__file__)),
        families=families,records=output,unavailable=unavailable,all_saved_point_metrics_reproduced=True,selection_changed=False,random_construction_seeds_not_counted_as_cases=True))
    print(json.dumps(dict(status='CONTROL_COMPARISONS_COMPLETE',contrasts=len(output))),flush=True)

if __name__=='__main__':main()
