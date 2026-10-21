"""CPU audit of committed formed-candidate arrays and actual target exports."""
from r3_common import *
import argparse


def audit(path):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    result_path=Path(path);result=read(result_path);task=result['task']
    assert result['status']=='COMPLETE'
    pack_path=Path(task['pack']);assert sha(pack_path)==task['pack_sha256'];pack=read(pack_path)
    ids=['Base']+[e['id'] for e in pack['entries']];prior_path=Path(task['first42_summary'])
    assert sha(prior_path)==task['first42_summary_sha256'];summary=read(prior_path)
    old_scores=np.load(ROOT/summary['artifacts']['scores.npy']['path'],mmap_mode='r',allow_pickle=False)
    old_trajectories=np.load(ROOT/summary['artifacts']['trajectories.npy']['path'],mmap_mode='r',allow_pickle=False)
    checks=[]
    assert task['seeds']==[0,1,2,3,4] and pack['candidate_scope']=='formed'
    for ref in result['cases']:
        case_path=ROOT/ref['path'];assert sha(case_path)==ref['sha256'];d=read(case_path)
        assert d['status']=='COMPLETE' and d['candidate_ids']==ids and d['fields']==FIELDS
        assert d['pack_sha256']==task['pack_sha256'] and d['seeds']==[0,1,2,3,4]
        assert d['no_external_failure_gate'] and d['no_extra_safety_filter'] and d['R3_evaluation_not_used_for_selection']
        for k in ['numeric','interfaces']:assert sha(ROOT/d[k]['path'])==d[k]['sha256']
        with np.load(ROOT/d['numeric']['path'],allow_pickle=False) as z:
            q=np.array(z['scores']);t=np.array(z['trajectories']);edits=np.array(z['relative_edits']);sources=np.array(z['actual_sources'])
        assert q.dtype==np.float64 and t.dtype==np.float32 and edits.dtype==np.float64
        assert q.shape==(len(ids),5,7) and t.shape==(len(ids),5,8,3) and edits.shape==(len(ids),5) and sources.shape==(len(ids),5)
        assert np.isfinite(q).all() and np.isfinite(t).all() and np.isfinite(edits).all() and (edits>=0).all()
        assert (q>=0).all() and (q<=1+1e-8).all() and (np.char.str_len(sources)>0).all()
        expected=q[:,:,1]*q[:,:,2]*(5*q[:,:,4]+5*q[:,:,3]+2*q[:,:,5])/12
        assert np.max(np.abs(expected-q[:,:,0]))<1e-8
        index=d['global_index'];old=old_scores[index,:,:,0]
        assert np.array_equal(q[0],old_scores[index,0]) and np.array_equal(t[0],old_trajectories[index,0])
        def winner(noises):
            use=list(noises);quality=q[:,use,0].mean(1);amount=edits[:,use].mean(1)
            tied=np.flatnonzero(quality==quality.max())
            return int(min(tied,key=lambda i:(ids[i]!='Base',float(amount[i]),ids[i])))
        chosen=[winner([j]) for j in range(5)]+[winner(range(5)),winner(range(3))]
        selections=d['selection']
        assert selections['R1']==[dict(arm=ids[i],seed_index=j) for j,i in enumerate(chosen[:5])]
        assert selections['R2']==[dict(arm=ids[chosen[5]],seed_index=j) for j in range(5)]
        assert selections['R3']==[dict(arm=ids[chosen[6]],seed_index=j) for j in [3,4]]
        assert selections['R3_selection_seeds']==[0,1,2] and selections['R3_evaluation_seeds']==[3,4]
        needed=set()
        for j,i in enumerate(chosen[:5]):
            bound=old[:,j].max();value=q[i,j,0]
            if i!=0 and (value>bound or (value==bound and old[0,j]<bound)):needed.add((i,j))
        for offset,noises in [(5,range(5)),(6,range(3))]:
            i=chosen[offset];use=list(noises);values=old[:,use].mean(1);value=q[i,use,0].mean()
            if i!=0 and (value>values.max() or (value==values.max() and values[0]<values.max())):needed.update((i,j) for j in range(5))
        expected_keys={ids[i]+'_S'+str(j) for i,j in needed}
        assert set(d['teacher_records'])==expected_keys
        with np.load(ROOT/d['interfaces']['path'],allow_pickle=False) as z:
            positions=z['valid_token_positions'];assert positions.ndim==1 and len(positions)>0 and np.array_equal(np.unique(positions),positions)
            assert z['input_ids'].ndim==1 and int(positions.max())<len(z['input_ids'])
            for i,j in needed:
                target=d['teacher_records'][ids[i]+'_S'+str(j)];h=z[target['interface_array']]
                assert target['arm']==ids[i] and target['seed_index']==j and target['seed']==seed(d['token'],j)
                assert target['same_execution_interface'] and h.dtype==np.float32 and h.shape==(len(positions),384) and np.isfinite(h).all()
                assert hashlib.sha256(h.tobytes()).hexdigest()==target['interface_sha256']
                assert target['trajectory']==t[i,j].tolist() and [target['score'][f] for f in FIELDS]==q[i,j].tolist()
                assert target['actual_source']==str(sources[i,j])
        checks.append(dict(token=d['token'],global_index=index,records=len(ids)*5,teacher_exports=len(needed),selection=chosen))
    assert [c['global_index'] for c in checks]==task['indices']
    return dict(status='PASS_GENERIC_CPU_AUDIT',time=stamp(),result_path=str(result_path.relative_to(ROOT)),result_sha256=sha(result_path),checks=checks,
                all_branches_and_three_choices_verified=True,all_competitive_actual_targets_present=True,no_GT_used=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--result',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=ROOT/a.output;assert not output.exists();proof=audit(Path(a.result).resolve());atomic(output,proof)
    print(json.dumps(dict(status=proof['status'],cases=len(proof['checks']),records=sum(c['records'] for c in proof['checks']),teacher_exports=sum(c['teacher_exports'] for c in proof['checks']))),flush=True)
