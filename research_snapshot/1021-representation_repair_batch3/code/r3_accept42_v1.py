"""Independent coverage, selectors and same-execution teacher-asset verification."""
from r3_common import *
import argparse
from collections import Counter


def main(a):
    import numpy as np
    stage=ROOT/'runs'/a.stage;producer=read(stage/'producer.json');tasks=read(stage/'tasks.json');pack=read(ROOT/'manifests/first42_v1.json')
    expected={i for t in tasks for i in t.get('indices',range(t.get('start',0),t.get('end',0)))}
    assert len(tasks)==producer['tasks'] and len(expected)==producer['cases']
    records=Counter();rows={};sources=[];endpoints={k:[] for k in ['Base','R1','R2','R3','Base_S3S4','Base_best5']}
    accepted=stage/'AGENT_ACCEPTANCE.json';assert not accepted.exists()
    for task in tasks:
        receipt=stage/'receipts'/(task['id']+'.json');r=read(receipt);assert r['status']=='COMPLETE'
        path=ROOT/r['result']['path'];assert sha(path)==r['result']['sha256'];result=read(path)
        cases=result.get('cases')
        assert isinstance(cases,list)
        for case in cases:
            p=ROOT/case['path'];assert sha(p)==case['sha256'];d=read(p);index=d['global_index'];assert index in expected and index not in rows;rows[index]=d['token']
            assert d['pack_sha256']==sha(ROOT/'manifests/first42_v1.json') and d['no_external_failure_gate'] and d['no_extra_safety_filter']
            lookup={(v['arm'],v['seed_index']):v for v in d['records']}
            assert len(lookup)==210 and set(lookup)=={(e['id'],j) for e in pack['entries'] for j in range(5)}
            scores=np.asarray([[lookup[(e['id'],j)]['score']['score'] for j in range(5)] for e in pack['entries']],dtype=np.float64)
            assert np.isfinite(scores).all()
            for name,values,noise in [('R1',scores,range(5)),('R2',scores.mean(1),[0]),('R3',scores[:,:3].mean(1),[0])]:
                choices=d['selection'][name]
                if name=='R1':assert all(lookup[(v['arm'],v['seed_index'])]['score']['score']==scores[:,v['seed_index']].max() for v in choices)
                else:
                    assert len({v['arm'] for v in choices})==1;ident=choices[0]['arm'];column=next(i for i,e in enumerate(pack['entries']) if e['id']==ident)
                    assert values[column]==values.max()
                for v in choices:
                    pair=v['arm']+'_S'+str(v['seed_index']);teacher=d['teacher_records'][pair];raw=lookup[(v['arm'],v['seed_index'])]
                    assert teacher['trajectory']==raw['trajectory'] and teacher['score']==raw['score'] and teacher['same_execution_interface']
                endpoints[name].append([lookup[(v['arm'],v['seed_index'])]['score']['score'] for v in choices])
            native=scores[0];endpoints['Base'].append(native.tolist());endpoints['Base_S3S4'].append(native[3:].tolist());endpoints['Base_best5'].append([float(native.max())])
            file=ROOT/d['interfaces']['path'];assert sha(file)==d['interfaces']['sha256']
            with np.load(file,allow_pickle=False) as z:
                positions=z['valid_token_positions'];assert len(positions)>0 and np.array_equal(positions,np.unique(positions))
                for teacher in d['teacher_records'].values():
                    array=z[teacher['interface_array']];assert array.dtype==np.float32 and array.shape==(len(positions),384) and np.isfinite(array).all()
                    assert hashlib.sha256(array.tobytes()).hexdigest()==teacher['interface_sha256']
            records['cases']+=1;records['records']+=len(lookup);records['teacher_records']+=len(d['teacher_records'])
        sources.append(dict(path=str(receipt.relative_to(ROOT)),sha256=sha(receipt)))
    assert set(rows)==expected
    summary={k:float(np.mean(v)*100) for k,v in endpoints.items()}
    summary.update(R1_gain=summary['R1']-summary['Base'],R2_gain=summary['R2']-summary['Base'],R3_gain=summary['R3']-summary['Base_S3S4'])
    atomic(accepted,dict(status='PASS_EXACT_COVERAGE_SELECTORS_AND_SAME_EXECUTION_TEACHER_ASSETS',time=stamp(),stage=a.stage,counts=dict(records),summary=summary,
                         pack_sha256=sha(ROOT/'manifests/first42_v1.json'),sources=sources,R3_negative_evaluation_retained=True,teacher_snapshot_frozen=False))
    print(json.dumps(dict(status='PASS',stage=a.stage,counts=dict(records),summary=summary)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
