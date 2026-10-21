"""Collect exact golden proofs or compute concurrency phase measurements.

Mechanical evidence only: the agent decides whether throughput justifies the
expansion. No worker signals, cloud calls, or scientific output modifications.
"""
from r3_common import *
import argparse
import statistics
from collections import defaultdict


def main(a):
    path=ROOT/'resources'/(a.group+'.json');group=read(path);proofs=[]
    for setting in group['workers']:
        p=ROOT/'runs/extra_engineering_v1'/setting['worker']/'PASS.json';d=read(p);w=d['worker']
        assert d['status']=='PASS_ALL42_FIVE_NOISE_GOLDEN_EXACT' and d['freeze_unchanged']
        assert w['worker']==setting['worker'] and w['node']==setting['node'] and w['device']==setting['device'] and w['lane']==setting['lane']
        assert d['result']['records']==420 and sha(ROOT/d['result']['path'])==d['result']['sha256']
        proofs.append(dict(worker=w['worker'],node=w['node'],device=w['device'],pid=w['pid'],pass_sha256=sha(p)))
    if a.mode=='admission':
        result=dict(status='PASS_ADDED_LANES_42X5_GOLDEN_EXACT',time=stamp(),group=a.group,
                    extra_workers=len(proofs),proofs=proofs,extra_engineering_records=420*len(proofs),
                    physical_cards_added=0,worker_program_sha256=sha(ROOT/'code/r3_extra_worker_v2.py'),
                    drainable_driver_sha256=sha(ROOT/'code/r3_first42_driver_v2.py'),
                    frozen_evaluation_sha256=sha(ROOT/'code/r3_first42_rollout_v2.py'))
        output=ROOT/'provenance'/(a.group+'_ACCEPTANCE.json');assert not output.exists();atomic(output,result)
        print(json.dumps({k:v for k,v in result.items() if k!='proofs'}),flush=True);return
    stage=ROOT/'runs/first42_navtrain_v1';now=dt.datetime.now(dt.timezone.utc)
    target_nodes={v['node'] for v in group['workers']}
    registry=read(ROOT/'resources/REGISTRY.json');hosts={n['job']+'-master-0':n['name'] for n in registry['nodes']}
    before=group['pre_expansion_records'];after=[];paths=list((stage/'receipts').glob('*.json'))
    for p in paths:
        if p.stat().st_mtime<now.timestamp()-a.window:continue
        r=read(p);end=dt.datetime.fromisoformat(r['time']).timestamp()
        if end-r['seconds']<now.timestamp()-a.window or end>now.timestamp():continue
        assert r['result']['cases']==len(r['task']['indices'])
        after.append(dict(path=str(p.relative_to(ROOT)),time=r['time'],worker=r['worker'],cases=r['result']['cases'],seconds=r['seconds']))
    samples=defaultdict(list);counts=defaultdict(int);by_node=defaultdict(int)
    for phase,records in [('before',before),('after',after)]:
        for r in records:
            w=r['worker'];node=hosts[w['hostname']]
            if w.get('bounded_trial'):continue
            if group.get('exclude_device15_from_before_after_node_comparison_due_prior_trial') and node in target_nodes and str(w['device'])=='15':continue
            category='target' if node in target_nodes else 'control'
            key=(phase,category,w['hostname'],w['pid']);samples[key].append(r['seconds']/r['cases'])
            counts[(phase,category)]+=r['cases'];by_node[(phase,node)]+=r['cases']
    rates=defaultdict(float);workers=defaultdict(int);minimum_chunks=defaultdict(list)
    for key,values in samples.items():
        phase,category,host,pid=key;rates[(phase,category)]+=1/statistics.mean(values)
        workers[(phase,category)]+=1;minimum_chunks[(phase,category)].append(len(values))
    target_ratio=rates[('after','target')]/rates[('before','target')]
    control_ratio=rates[('after','control')]/rates[('before','control')]
    failed=list((stage/'failures').glob('*.json'))+list((stage/'audit_v1/failures').glob('*.json'))
    result=dict(status='PHASE_MEASUREMENTS_REQUIRE_AGENT_REVIEW',time=stamp(),group=a.group,
                same_target_aggregate_speedup=target_ratio,control_adjusted_speedup=target_ratio/control_ratio,
                rates={phase+'_'+category:v for (phase,category),v in rates.items()},
                distinct_workers={phase+'_'+category:v for (phase,category),v in workers.items()},
                minimum_chunks_per_worker={phase+'_'+category:min(v) for (phase,category),v in minimum_chunks.items()},
                after_window_seconds=a.window,before_window_seconds=group['pre_expansion_window_seconds'],
                recent_cases_per_second=sum(r['cases'] for r in after)/a.window,
                committed_chunks=len(paths),audited_chunks=len(list((stage/'audit_v1/shards').glob('*.json'))),
                failures=len(failed),physical_cards=48,raw_receipts_for_review=after,
                excluding_target_device15=group.get('exclude_device15_from_before_after_node_comparison_due_prior_trial',False))
    output=ROOT/'provenance'/(a.group+'_PHASE_MEASUREMENTS.json');assert not output.exists();atomic(output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='raw_receipts_for_review'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',required=True);p.add_argument('--mode',choices=['admission','phase'],required=True);p.add_argument('--window',type=int,default=240);main(p.parse_args())
