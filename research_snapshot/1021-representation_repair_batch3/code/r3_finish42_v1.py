"""Assemble independently audited scores and report train+validation as primary.

Invoked by the agent after complete coverage, never by a timer. This does not
release resources, submit tests or freeze a new teacher snapshot automatically.
"""
from r3_common import *
import argparse
from collections import Counter


def summarize(q,c,rows,positions):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    p=np.asarray(positions,dtype=np.int64);x=np.asarray(q[p]);choice=np.asarray(c[p]);n=len(p);scene=np.arange(n)
    base=x[:,0];r1=np.stack([x[scene,choice[:,j],j] for j in range(5)],axis=1)
    r2=x[scene,choice[:,5]];r3=x[scene,choice[:,6]][:,3:]
    assert np.all(r1[:,:,0]>=base[:,:,0]) and np.all(r1[:,:,0].mean(1)>=r2[:,:,0].mean(1)-1e-15)
    assert np.all(r2[:,:,0].mean(1)>=base[:,:,0].mean(1)-1e-15)
    sessions=np.asarray([rows[int(i)]['session'] for i in p]);unique,session_index=np.unique(sessions,return_inverse=True)
    sizes=np.bincount(session_index);rng=np.random.default_rng(2026102101)
    weights=rng.multinomial(len(unique),np.full(len(unique),1/len(unique)),size=2000)
    output={}
    for name,after,before,noises in [('R1',r1,base,[0,1,2,3,4]),('R2',r2,base,[0,1,2,3,4]),('R3',r3,base[:,3:],[3,4])]:
        delta=after[:,:,0]-before[:,:,0];case_delta=delta.mean(1);sums=np.bincount(session_index,weights=case_delta)
        bootstrap=(weights@sums)/(weights@sizes)*100
        events={}
        for field in ['no_at_fault_collisions','drivable_area_compliance','time_to_collision_within_bound']:
            col=FIELDS.index(field);new=(after[:,:,col]<1)&(before[:,:,col]>=1);removed=(after[:,:,col]>=1)&(before[:,:,col]<1)
            events[field]=dict(new=int(new.sum()),removed=int(removed.sum()),net=int(new.sum()-removed.sum()))
        output[name]=dict(cases=n,outputs=int(n*len(noises)),noise_indices=noises,PDMS=float(after[:,:,0].mean()*100),Base_PDMS=float(before[:,:,0].mean()*100),
                          gain=float(delta.mean()*100),PDMS_by_noise=(after[:,:,0].mean(0)*100).tolist(),Base_PDMS_by_noise=(before[:,:,0].mean(0)*100).tolist(),
                          session_bootstrap_gain_CI95=np.quantile(bootstrap,[.025,.975]).tolist(),
                          mean_score_components={f:float(after[:,:,j].mean()) for j,f in enumerate(FIELDS)},safety_events=events,
                          high_outputs_above90=int((after[:,:,0]>.9).sum()),failure_outputs_below70=int((after[:,:,0]<.7).sum()),zero_outputs=int((after[:,:,0]==0).sum()),
                          Base_high_to_failure=int(((before[:,:,0]>.9)&(after[:,:,0]<.7)).sum()),Base_high_to_not_high=int(((before[:,:,0]>.9)&(after[:,:,0]<=.9)).sum()),
                          positive_mean_scenes=int((case_delta>0).sum()),negative_mean_scenes=int((case_delta<0).sum()),zero_mean_scenes=int((case_delta==0).sum()),
                          all_evaluation_draws_above90=int((after[:,:,0]>.9).all(1).sum()))
    u1=(r1[:,:,0]<.9).any(1);u2=r2[:,:,0].mean(1)<.9
    # No S3/S4 is used to build the separate R3 prescreen pool.
    r3_per_noise=x[:,:,:3,0].max(1);r3_fixed=x[:,:,:3,0].mean(2).max(1)
    return dict(cases=n,sessions=len(unique),endpoints=output,Base_mean_PDMS=float(base[:,:,0].mean()*100),Base_best_of_five_PDMS=float(base[:,:,0].max(1).mean()*100),
                unresolved=dict(U1_any_per_draw_oracle_below90=int(u1.sum()),U2_fixed_five_mean_below90=int(u2.sum()),union=int((u1|u2).sum()),U2_only=int((u2&~u1).sum())),
                R3_first_three_unresolved=int(((r3_per_noise<.9).any(1)|(r3_fixed<.9)).sum()))


def main(a):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    stage=ROOT/'runs'/a.stage;producer=read(stage/'producer.json');tasks=read(stage/'tasks.json');pack_path=ROOT/'manifests/first42_v1.json';pack=read(pack_path)
    rows=read(producer['rows']);assert sha(producer['rows'])==producer['rows_sha256'] and sha(pack_path)==producer['pack_sha256']
    if not a.engineering:assert len(rows)==(103288 if producer['cohort']=='navtrain' else 12146)
    target=ROOT/'analysis'/a.stage;assert not target.exists();target.mkdir(parents=True)
    expected={i for t in tasks for i in t['indices']};matrix_rows=max(expected)+1
    scores=np.lib.format.open_memmap(target/'scores.npy',mode='w+',dtype=np.float64,shape=(matrix_rows,42,5,7))
    trajectories=np.lib.format.open_memmap(target/'trajectories.npy',mode='w+',dtype=np.float32,shape=(matrix_rows,42,5,8,3))
    selected=np.lib.format.open_memmap(target/'selected.npy',mode='w+',dtype=np.int64,shape=(matrix_rows,7))
    seen=np.zeros(matrix_rows,dtype=bool);sources=[];case_index=[]
    assert len(tasks)==producer['tasks'] and len(expected)==producer['cases']
    for task in tasks:
        proof_path=stage/'audit_v1/shards'/(task['id']+'.json');proof=read(proof_path)
        assert proof['status']=='PASS' and proof['pack_sha256']==producer['pack_sha256'] and proof['fields']==FIELDS and proof['candidate_ids']==[e['id'] for e in pack['entries']]
        assert proof['indices']==task['indices']
        array=ROOT/proof['array'];assert sha(array)==proof['array_sha256']
        with np.load(array,allow_pickle=False) as z:
            idx=z['indices'];assert not seen[idx].any() and idx.tolist()==proof['indices']
            scores[idx]=z['scores'];trajectories[idx]=z['trajectories'];selected[idx]=z['selected'];seen[idx]=True
        for offset,i in enumerate(proof['indices']):
            assert proof['tokens'][offset]==rows[i]['token'] and proof['sessions'][offset]==rows[i]['session']
            case_index.append(dict(global_index=i,token=rows[i]['token'],subset=proof['subsets'][offset],**proof['case_proofs'][offset]))
        sources.append(dict(path=str(proof_path.relative_to(ROOT)),sha256=sha(proof_path)))
    assert set(np.flatnonzero(seen))==expected
    scores.flush();trajectories.flush();selected.flush()
    groups={'navtrain_all' if producer['cohort']=='navtrain' else 'navtest':sorted(expected)}
    if producer['cohort']=='navtrain':
        for subset in ['exploration','validation']:groups[subset]=[i for i in sorted(expected) if rows[i]['subset']==subset]
    results={name:summarize(scores,selected,rows,idx) for name,idx in groups.items() if idx}
    all_idx=np.asarray(sorted(expected),dtype=np.int64);x=np.asarray(scores[all_idx,:,:,0]);choices=np.asarray(selected[all_idx]);scene=np.arange(len(all_idx))
    oracle1=x.max(1);fixed=x[scene,choices[:,5]].mean(1)
    u1=(oracle1<.9).any(1);u2=fixed<.9
    first3= x[:,:,:3];r3u1=(first3.max(1)<.9).any(1);r3u2=first3.mean(2).max(1)<.9
    pool=dict(status='FROZEN_REFERENCE_POOL_NOT_CANDIDATE_SELECTION',time=stamp(),cohort=producer['cohort'],source_stage=a.stage,reference_pack_sha256=producer['pack_sha256'],threshold=.9,
              U1_indices=all_idx[u1].tolist(),U2_indices=all_idx[u2].tolist(),union_indices=all_idx[u1|u2].tolist(),
              R3_first_three_U1_indices=all_idx[r3u1].tolist(),R3_first_three_U2_indices=all_idx[r3u2].tolist(),R3_first_three_union_indices=all_idx[r3u1|r3u2].tolist(),
              test_cannot_supply_expansion_pool=producer['cohort']=='navtest',formed_candidates_exempt_from_prescreen=True)
    atomic(target/'UNRESOLVED_POOLS.json',pool);atomic(target/'CASE_INDEX.json',sorted(case_index,key=lambda v:v['global_index']))
    paths={name:dict(path=str((target/name).relative_to(ROOT)),sha256=sha(target/name)) for name in ['scores.npy','trajectories.npy','selected.npy','CASE_INDEX.json','UNRESOLVED_POOLS.json']}
    summary=dict(status='PASS_COMPLETE_AUDITED_FIRST42' if not a.engineering else 'PASS_ENGINEERING_ONLY',time=stamp(),stage=a.stage,cohort=producer['cohort'],cases=len(expected),entries=42,seeds=[0,1,2,3,4],
                 pack_sha256=producer['pack_sha256'],rows=producer['rows'],rows_sha256=producer['rows_sha256'],results=results,artifacts=paths,sources=sources,primary_cohort='navtrain_all_103288_including_validation',
                 no_external_failure_gate=True,no_extra_safety_filter=True,R3_negative_evaluation_retained=True,R3_evaluation_not_used_for_choice=True,teacher_snapshot_frozen=False)
    atomic(target/'SUMMARY.json',summary)
    acceptance=stage/'AGENT_ACCEPTANCE.json'
    if not acceptance.exists():atomic(acceptance,dict(status=summary['status'],time=stamp(),summary=str((target/'SUMMARY.json').relative_to(ROOT)),summary_sha256=sha(target/'SUMMARY.json')))
    print(json.dumps(dict(status=summary['status'],cases=len(expected),results={name:{k:round(v['PDMS'],6) for k,v in value['endpoints'].items()} for name,value in results.items()})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--engineering',action='store_true');main(p.parse_args())
