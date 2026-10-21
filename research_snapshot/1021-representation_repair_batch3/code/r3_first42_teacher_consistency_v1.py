"""CPU-only actual interface identity consistency across the five selected draws.

Hashes come from the complete, independently audited actual executions. This
does not average hidden states, select methods, or create a teacher snapshot.
"""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from collections import Counter


def inspect(path):
    d=read(path);lookup={(r['arm'],r['seed_index']):r for r in d['records']};output={}
    for endpoint in ['R1','R2','R3']:
        pairs=d['selection'][endpoint]
        if endpoint=='R3':pairs=[dict(arm=pairs[0]['arm'],seed_index=j) for j in range(5)]
        records=[lookup[v['arm'],v['seed_index']] for v in pairs]
        hashes=[r['interface_sha256'] for r in records]
        output[endpoint]=dict(unique_interfaces=len(set(hashes)),unique_methods=len({r['arm'] for r in records}),
                              changed_from_Base=any(r['arm']!='Base' for r in records),
                              all_five_PDMS_above90=all(r['score']['score']>.9 for r in records),
                              methods=[r['arm'] for r in records],interface_hashes=hashes)
    return dict(token=d['token'],global_index=d['global_index'],subset=d['subset'],session=d['session'],
                Base_S0_quality=lookup['Base',0]['score']['score'],endpoints=output)


def main(a):
    stage=ROOT/'runs'/a.stage;accepted=read(stage/'AGENT_ACCEPTANCE.json')
    assert accepted['status']=='PASS_COMPLETE_AUDITED_FIRST42'
    summary=read(ROOT/accepted['summary']);assert sha(ROOT/accepted['summary'])==accepted['summary_sha256']
    index_path=ROOT/summary['artifacts']['CASE_INDEX.json']['path'];assert sha(index_path)==summary['artifacts']['CASE_INDEX.json']['sha256']
    cases=read(index_path);destination=ROOT/'analysis'/a.stage/'TEACHER_CONSISTENCY.json';assert not destination.exists()
    paths=[str(ROOT/c['path']) for c in cases];results=[]
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn')) as pool:
        for value in pool.map(inspect,paths,chunksize=32):results.append(value)
    assert len(results)==summary['cases'] and len({r['token'] for r in results})==len(results)
    groups={'navtrain_all' if summary['cohort']=='navtrain' else 'navtest':results}
    if summary['cohort']=='navtrain':
        groups.update({name:[r for r in results if r['subset']==name] for name in ['exploration','validation']})
    output={}
    for name,rows in groups.items():
        output[name]=dict(cases=len(rows),endpoints={endpoint:dict(
            distinct_interface_count_distribution=dict(Counter(str(r['endpoints'][endpoint]['unique_interfaces']) for r in rows)),
            all_five_interface_identical=sum(r['endpoints'][endpoint]['unique_interfaces']==1 for r in rows),
            changed_from_Base=sum(r['endpoints'][endpoint]['changed_from_Base'] for r in rows),
            all_five_PDMS_above90_and_interface_identical=sum(r['endpoints'][endpoint]['unique_interfaces']==1 and r['endpoints'][endpoint]['all_five_PDMS_above90'] for r in rows)) for endpoint in ['R1','R2','R3']})
    atomic(destination,dict(status='COMPLETE_ACTUAL_INTERFACE_IDENTITY_ANALYSIS',time=stamp(),source_summary_sha256=accepted['summary_sha256'],
           results=output,cases=results,interface_equality='Byte identity of actual float32 valid-token tensors, not semantic similarity',
           R3_interface_consistency_uses_five_actual_outputs_for_diagnosis_only=True,no_selection_or_snapshot_changes=True))
    print(json.dumps(dict(status='COMPLETE_ACTUAL_INTERFACE_IDENTITY_ANALYSIS',results=output)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--workers',type=int,default=4);main(p.parse_args())
