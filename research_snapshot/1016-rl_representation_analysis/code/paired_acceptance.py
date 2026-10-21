"""Coverage, tensor, score and device-independent replay checks for paired observations."""
from common import *
import argparse
from collections import Counter,defaultdict
import subprocess


def load_records(run,phase):
    base=ROOT/'runs'/run/phase
    return [r for p in sorted(base.glob('rank*/records.json')) for r in read(p)]


def summarize(records,protocol):
    import numpy as np
    paired=defaultdict(dict)
    for r in records:
        key=(r['token'],r['noise_group'],r['start_t'])
        assert r['source'] not in paired[key]
        paired[key][r['source']]=r
        assert r['identity']==protocol['identity']
        assert r['quality']==quality(r['score']['score'])
    stats=[]
    for t0 in sorted({r['start_t'] for r in records}):
        group=[v for k,v in paired.items() if k[2]==t0]
        combinations=Counter();changes=defaultdict(list)
        for p in group:
            assert set(p)=={'baseline_failure','GT'}
            a,b=p['baseline_failure'],p['GT']
            assert a['noise_seeds']==b['noise_seeds'] and a['array_path']==b['array_path']
            assert a['feature_sha256']==b['feature_sha256']
            combinations[(a['quality'],b['quality'])]+=1
            for r in [a,b]:
                changes[r['source']].append(r['score']['score'])
        stats.append(dict(start_t=t0,pairs=len(group),
            combinations=[dict(failure_initialized=a,gt_initialized=b,count=n) for (a,b),n in sorted(combinations.items())],
            final_high_fail_pairs=sum(n for (a,b),n in combinations.items() if {a,b}=={'failure','high_quality'}),
            original_orientation_pairs=combinations[('failure','high_quality')],
            reversed_orientation_pairs=combinations[('high_quality','failure')],
            mean_pdms_100={s:float(np.mean(v)*100) for s,v in changes.items()}))
    return dict(candidates=len(records),scenes=len({r['token'] for r in records}),pairs=len(paired),
                quality_counts=dict(Counter(r['quality'] for r in records)),by_start_t=stats,
                subsets=dict(Counter(r['subset'] for r in records)),
                original_gt_not_gt90_scenes_retained=len({r['token'] for r in records if r['original_gt_score']['score']<=.9}),
                original_gt_gate_applied=False,labels_assigned_after_complete_denoising_rescore=True)


def accept(args):
    import numpy as np
    protocol=read(args.protocol);records=load_records(args.run,args.phase)
    refs=read(ROOT/protocol['references'])
    wanted=set(protocol['pilot_tokens']) if args.phase=='pilot' else {r['token'] for r in refs}
    starts=protocol[f'{args.phase}_start_timesteps']
    keys={(r['token'],r['noise_group'],r['start_t'],r['source']) for r in records}
    expected={(token,g,t,s) for token in wanted for g in protocol['noise_groups'] for t in starts for s in ['baseline_failure','GT']}
    assert keys==expected and len(records)==len(keys),(len(keys),len(expected))
    arrays={r['array_path']:r['array_sha256'] for r in records};bytes_total=0
    for i,(path,hashed) in enumerate(arrays.items(),1):
        assert sha(path)==hashed,path
        with np.load(path,allow_pickle=False) as data:
            a=data['representations'];times=data['timesteps']
            assert a.shape==(2,len(times),18,8,384) and a.dtype==np.float32 and np.isfinite(a).all()
            assert data['dit_output'].shape==(2,len(times),8,512)
            assert data['predicted_noise'].shape==(2,len(times),8,3)
            assert np.isfinite(data['dit_output']).all()
            assert np.isfinite(data['predicted_noise']).all()
        bytes_total+=Path(path).stat().st_size
        if i%256==0:print(json.dumps(dict(checked_arrays=i,total=len(arrays))),flush=True)
    bykey={(r['token'],r['noise_group'],r['start_t'],r['source']):r for r in records}
    for r in records:
        with np.load(r['array_path'],allow_pickle=False) as data:
            assert np.array_equal(data['final_trajectories'][r['branch_index']],np.asarray(r['trajectory'],dtype=np.float32))
    if args.anchor_run:
        anchor=load_records(args.anchor_run,args.phase)
        assert len(anchor)==len(records)
        for a in anchor:
            b=bykey[(a['token'],a['noise_group'],a['start_t'],a['source'])]
            assert a['trajectory']==b['trajectory'] and a['score']==b['score']
            with np.load(a['array_path'],allow_pickle=False) as x,np.load(b['array_path'],allow_pickle=False) as y:
                assert set(x.files)==set(y.files)
                assert all(np.array_equal(x[k],y[k]) for k in x.files),(a['token'],a['noise_group'],a['start_t'])
    out=ROOT/'runs'/args.run/f'{args.phase}_acceptance';out.mkdir(parents=True,exist_ok=True)
    # Independently verify each source, start, group and baseline failure mode where available.
    probes=[];covered=set()
    for r in sorted(records,key=lambda r:digest([r['token'],r['source'],r['noise_group'],r['start_t']])):
        cell=(r['source'],r['noise_group'],r['start_t'],r['primary_mode'])
        if cell not in covered:covered.add(cell);probes.append(r)
    refs_by={r['token']:r for r in refs};cfg=read(ROOT/'configs/baseline.json')
    tasks=[dict(token=r['token'],source=r['source'],trajectory=r['trajectory'],
                metric_cache=refs_by[r['token']]['metric_cache'],metric_sha256=refs_by[r['token']]['metric_sha256'],scoring=cfg['scoring']) for r in probes]
    atomic(out/'independent_request.json',tasks)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/representation_prepare.py'),'score',
        '--request',str(out/'independent_request.json'),'--response',str(out/'independent_scores.json'),
        '--original-source',cfg['shared_reference_source']],check=True,cwd=ROOT,timeout=600)
    actual=read(out/'independent_scores.json')['results']
    assert len(actual)==len(probes)
    for r,s in zip(probes,actual):assert r['score']==s['score']
    result=dict(status='PASS',time=stamp(),run=args.run,phase=args.phase,**summarize(records,protocol),
                arrays=len(arrays),array_bytes=bytes_total,all_arrays_hash_finite_shape_valid=True,
                original_source_independent_rescore_count=len(probes),independent_score_max_delta=0,
                anchor_run=args.anchor_run,all_anchor_tensors_and_outputs_exact=bool(args.anchor_run),test_cache_access=False)
    atomic(out/'ACCEPTANCE.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--phase',choices=['pilot','formal'],required=True)
    p.add_argument('--protocol',required=True,type=Path);p.add_argument('--anchor-run');args=p.parse_args()
    setup(f'{args.run}/{args.phase}_acceptance');compatibility();accept(args)
