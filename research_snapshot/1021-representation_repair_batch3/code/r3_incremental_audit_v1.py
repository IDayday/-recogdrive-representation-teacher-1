"""CPU-only incremental audit of committed rollouts; no scientific selection.

Disjoint receipt claims permit several nodes to audit in parallel. Every score,
selector and selected interface is checked; compact numerical shards support
the final whole-training-set report without rereading the large JSON records.
"""
from r3_common import *
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
import multiprocessing as mp
import socket
import traceback

FIELDS=['score','no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound','ego_progress','comfort','driving_direction_compliance']


def initialize():setup('audit/'+socket.gethostname()+'/'+str(os.getpid()),threads=1)


def audit(arguments):
    import numpy as np
    receipt_path,stage_path=map(Path,arguments);stage=stage_path;audit_root=stage/'audit_v1'
    receipt=read(receipt_path);result_path=ROOT/receipt['result']['path'];assert sha(result_path)==receipt['result']['sha256'];result=read(result_path)
    pack=read(ROOT/'manifests/first42_v1.json');pack_sha=sha(ROOT/'manifests/first42_v1.json');entries=pack['entries'];ids=[e['id'] for e in entries]
    scores=[];trajectories=[];indices=[];tokens=[];subsets=[];sessions=[];selected=[];proofs=[];arrays_count=0
    assert receipt['status']=='COMPLETE' and result['status']=='COMPLETE'
    for ref in result['cases']:
        path=ROOT/ref['path'];assert sha(path)==ref['sha256'];d=read(path)
        assert d['pack_sha256']==pack_sha and d['no_external_failure_gate'] and d['no_extra_safety_filter'] and d['R3_evaluation_not_used_for_selection']
        lookup={(v['arm'],v['seed_index']):v for v in d['records']}
        assert len(lookup)==210 and set(lookup)=={(ident,j) for ident in ids for j in range(5)}
        q=np.asarray([[[lookup[(ident,j)]['score'][f] for f in FIELDS] for j in range(5)] for ident in ids],dtype=np.float64)
        t=np.asarray([[lookup[(ident,j)]['trajectory'] for j in range(5)] for ident in ids],dtype=np.float32)
        assert q.shape==(42,5,7) and t.shape==(42,5,8,3) and np.isfinite(q).all() and np.isfinite(t).all()
        assert (q>=0).all() and (q<=1+1e-8).all()
        calculated=q[:,:,1]*q[:,:,2]*(5*q[:,:,4]+5*q[:,:,3]+2*q[:,:,5])/12
        assert np.max(np.abs(calculated-q[:,:,0]))<1e-8
        edits=np.asarray([[lookup[(ident,j)]['relative_edit'] for j in range(5)] for ident in ids]);assert np.isfinite(edits).all()
        # First42 upstream operators have no action-noise input. Verify this
        # before reusing the same actual interface content across paired draws.
        assert np.all(edits==edits[:,:1])
        def chosen(values):
            high=values.max();equal=np.flatnonzero(values==high)
            return int(min(equal,key=lambda c:(ids[c]!='Base',float(edits[c,0]),ids[c])))
        c1=[chosen(q[:,j,0]) for j in range(5)];c2=chosen(q[:,:,0].mean(1));c3=chosen(q[:,:3,0].mean(1))
        expected=dict(R1=[(ids[c],j) for j,c in enumerate(c1)],R2=[(ids[c2],j) for j in range(5)],R3=[(ids[c3],j) for j in [3,4]])
        for endpoint,pairs in expected.items():assert [(v['arm'],v['seed_index']) for v in d['selection'][endpoint]]==pairs
        interface_path=ROOT/d['interfaces']['path'];assert sha(interface_path)==d['interfaces']['sha256']
        with np.load(interface_path,allow_pickle=False) as z:
            pos=z['valid_token_positions'];assert pos.ndim==1 and len(pos)>0 and np.array_equal(pos,np.unique(pos))
            for key,r in d['teacher_records'].items():
                raw=lookup[(r['arm'],r['seed_index'])];assert r['trajectory']==raw['trajectory'] and r['score']==raw['score'] and r['same_execution_interface']
                target=z[r['interface_array']];assert target.dtype==np.float32 and target.shape==(len(pos),384) and np.isfinite(target).all()
                assert hashlib.sha256(target.tobytes()).hexdigest()==r['interface_sha256'];arrays_count+=1
        scores.append(q);trajectories.append(t);indices.append(d['global_index']);tokens.append(d['token']);subsets.append(d['subset']);sessions.append(d['session']);selected.append(c1+[c2,c3])
        proofs.append(dict(path=str(path.relative_to(ROOT)),sha256=ref['sha256'],interfaces_sha256=d['interfaces']['sha256']))
    output=audit_root/'shards'/receipt_path.name;array=output.with_suffix('.npz');array.parent.mkdir(parents=True,exist_ok=True);assert not array.exists() and not output.exists()
    temporary=array.with_name(array.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('wb') as stream:np.savez_compressed(stream,scores=np.stack(scores),trajectories=np.stack(trajectories),indices=np.asarray(indices,dtype=np.int64),selected=np.asarray(selected,dtype=np.int64))
    temporary.replace(array)
    proof=dict(status='PASS',time=stamp(),receipt=str(receipt_path.relative_to(ROOT)),receipt_sha256=sha(receipt_path),result_sha256=receipt['result']['sha256'],
               pack_sha256=pack_sha,indices=indices,tokens=tokens,subsets=subsets,sessions=sessions,fields=FIELDS,candidate_ids=ids,
               array=str(array.relative_to(ROOT)),array_sha256=sha(array),case_proofs=proofs,teacher_records_verified=arrays_count,
               R3_selected_from_S0S1S2_only=True,all_selected_interfaces_verified=True)
    atomic(output,proof);return dict(path=str(output.relative_to(ROOT)),cases=len(indices),teacher_records_verified=arrays_count)


def main(a):
    initialize();stage=ROOT/'runs'/a.stage;folder=stage/'audit_v1';registry=read(ROOT/'resources/REGISTRY.json');node=next(n for n in registry['nodes'] if n['name']==a.node)
    assert socket.gethostname().startswith(node['job']+'-')
    live=folder/'workers'/(a.node+'.json');producer=read(stage/'producer.json');pending={};seen=set();count=0;cases=0
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        while True:
            for future in [v for v in pending if v.done()]:
                source=pending.pop(future)
                try:result=future.result();count+=1;cases+=result['cases']
                except BaseException as error:
                    atomic(folder/'failures'/source.name,dict(status='FAILED',time=stamp(),node=a.node,source=str(source),error=repr(error),traceback=traceback.format_exc()));raise
            for receipt in (stage/'receipts').glob('*.json'):
                if len(pending)>=a.workers*2:break
                if receipt.name in seen:continue
                seen.add(receipt.name)
                if (folder/'shards'/receipt.name).exists():continue
                claim=folder/'claims'/receipt.stem;claim.parent.mkdir(parents=True,exist_ok=True)
                try:claim.mkdir()
                except FileExistsError:continue
                atomic(claim/'OWNER.json',dict(time=stamp(),node=a.node,pid=os.getpid(),hostname=socket.gethostname(),receipt=str(receipt)))
                pending[pool.submit(audit,(str(receipt),str(stage)))]=receipt
            atomic(live,dict(status='RUNNING',time=stamp(),pid=os.getpid(),hostname=socket.gethostname(),node=a.node,workers=a.workers,audited_chunks=count,audited_cases=cases,pending=len(pending)))
            if len(list((folder/'shards').glob('*.json')))==producer['tasks']:
                final=dict(status='COMPLETE',time=stamp(),node=a.node,audited_chunks=count,audited_cases=cases)
                atomic(live,final);atomic(folder/('NODE_COMPLETE_'+a.node+'.json'),final)
                print(json.dumps(dict(event='ALL_CHUNKS_AUDITED',node=a.node,stage=a.stage)),flush=True);return
            if pending:wait(pending,timeout=10,return_when=FIRST_COMPLETED)
            else:time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=2);p.add_argument('--interval',type=int,default=60);main(p.parse_args())
