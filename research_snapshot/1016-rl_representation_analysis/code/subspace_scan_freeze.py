"""Freeze the complete analysis family after repair acceptance and backend engineering smoke."""
from common import *
import argparse
from subspace_scan_prepare import OUT,TIMES
from subspace_scan_math import KS,RS


def main(args):
    setup('subspace_scan/freeze')
    report_path=ROOT/'provenance/LATEST_REPAIR_REPORT_ACCEPTANCE.json'
    if not report_path.exists():report_path=ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json'
    report=read(report_path);assert report['status']=='PASS'
    assert sha(ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html')==report['report_sha256']
    assert read(ROOT/'repair_v1/FINAL_TEST_READY.json')['run']
    assert read(ROOT/'provenance/SUBSPACE_BACKEND_SMOKE.json')['status']=='PASS'
    assert read(ROOT/'provenance/SUBSPACE_REAL_ENGINEERING_SMOKE.json')['status']=='PASS'
    assert read(ROOT/'provenance/SUBSPACE_BACKEND_SMOKE.json')['selected_backend']==args.backend
    OUT.mkdir(parents=True,exist_ok=True);run='subspace_scan_20261016_v2';base=ROOT/'runs'/run;assert not base.exists();base.mkdir(parents=True)
    natural=read(ROOT/'manifests/natural_s0.json');pair=read(ROOT/'analysis/observation_v1/cache/metadata.json')
    atomic(OUT/'natural_metadata.json',[{k:r[k] for k in ['token','global_index','session','subset','quality','baseline_pdms_100']} for r in natural]);atomic(OUT/'paired_metadata.json',pair)
    tasks=[]
    for route in ['r1','r2']:
        for start in ([-1] if route=='r1' else TIMES):
            for step in (range(5) if route=='r1' else range(TIMES.index(start),5)):
                for layer in range(19):
                    for token in range(8):
                        row=dict(phase='cv',route=route,start=start,step=step,layer=layer,token=token)
                        row['id']='cv_'+digest(row)[:20];tasks.append(row)
    assert len(tasks)==3040
    # Interleave routes, starts and layers; dynamic claims keep both nodes productive.
    tasks.sort(key=lambda t:digest(dict(task=t,queue_root=20261016)))
    atomic(base/'tasks.json',tasks);atomic(base/'queue.json',dict(closed=False,reason='User explicitly retains primary queues and jobs'))
    protocol=dict(status='FROZEN',time=stamp(),ks=KS,kf=KS,r=RS,centering=['uncentered','pooled_centered'],
        cells=dict(route1=760,route2=2280),folds=5,fold_formula='int(sha256(canonical_json(session,cv_root=20261016))[:8],16)%5',
        fit='exploration fold training only; route2 P0 only; all input labels from final rescored outputs',
        probe='same projected class mean gap as previous observation; train-only scalar pooled variance normalization',
        controls='3 Gaussian-QR construction seeds per r; nested within seed; full-dimensional mean-gap probe',
        full_scope='9x9x8=648 requested residual combinations +24 random controls +1 full control per cell/center/fold',
        rank='class eigenvalue>max_eigen*1e-10; residual singular>1e-6; requested dims exceeding rank excluded, not silently padded or clipped; residual vectors QR reorthogonalized while preserving every prefix span',
        degenerate_cutoff='adjacent residual singular difference<=1e-8*max(first_singular,1): retain diagnostics, exclude arbitrary cutoff from region leaders',
        exploratory_multiplicity='BH across complete valid residual CV family separately per route; exploratory session t p only, dependent crossfits explicitly not confirmatory',
        confirmation_multiplicity='frozen small family; one-sided session sign-flip p and Holm correction per route including both centerings and equal/unequal families; 20000 flips',
        leader_eligibility=dict(auc_min=.60,standardized_gap_min=.20,fold_auc_min=.50,session_positive_fraction_min=.60,min_sessions=8,
            route2_min_common_endpoint_pairs=20,route2_P0_P1_ordering_min=.60,route2_ordering_gap_max=.10,route2_common_branch_order_agreement_min=.70),
        selection='Equal and unequal families separate; up to 2 nonoverlapping regions each route x centering x family. Rank by neighbor-median conservative AUC (P0/P1 min minus fold SD), then AP and session consistency. Freeze leader and immediate k_s/k_f/r grid neighbors, matching equal-dimension neighbors, same-r random controls, minimum feasible equal-main-dimension at each selected r, legacy k8/r8 anchor where feasible, and full-dimensional baseline before validation scoring.',
        no_model_collection=True,repair_report_sha256=report.get('report_sha256'))
    atomic(OUT/'PROTOCOL.json',protocol)
    old=read(ROOT/'configs/repair_execution_v2.json')
    paths=['code/common.py','code/natural_coordinate.py','code/paired_acceptance.py','code/subspace_results.py','code/subspace_golden_audit.py']+[str(p.relative_to(ROOT)) for p in sorted((ROOT/'code').glob('subspace_scan_*.py'))]
    cfg=dict(status='FROZEN',time=stamp(),run=run,score_backend=args.backend,cpu_threads_per_worker=read(ROOT/'provenance/SUBSPACE_BACKEND_SMOKE.json')['cpu_threads_per_worker'],code_sha256={p:sha(ROOT/p) for p in paths},submissions=old['submissions'],resources=old['resources'],
        protocol_sha256=sha(OUT/'PROTOCOL.json'),initial_tasks_sha256=sha(base/'tasks.json'),retain_resources=True,initial_tasks=len(tasks))
    cfg['workers_per_node']=16 if args.backend=='device_float64' else min(64,144//cfg['cpu_threads_per_worker'])
    cfg['identity']=digest(cfg);atomic(ROOT/'configs/subspace_scan_execution_v2.json',cfg)
    print(json.dumps(dict(status='FROZEN',run=run,tasks=len(tasks),backend=args.backend)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['cpu_float64','device_float64'],required=True);main(p.parse_args())
