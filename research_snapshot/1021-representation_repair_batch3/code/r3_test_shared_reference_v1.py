"""Read-only extraction of archived Base+30 test branches for exact replay checks.

This never selects or changes candidates. Scores are mapped by field names.
No archived teacher state is substituted for newly captured interfaces.
"""
from r3_common import *
import argparse
from concurrent.futures import ThreadPoolExecutor


def prepare():
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    from r3_first42_rollout_v2 import save_arrays
    stage=BATCH2/'runs/frozen_natural_test_batch2_three_roles_v1';spec=read(stage/'SPECIFICATION.json')
    lock=read(ROOT/'provenance/FIRST42_TEST_LOCK.json');assert spec['rows_sha256']==lock['test_rows_sha256'] and spec['seeds']==[0,1,2,3,4]
    rows=read(BATCH2/spec['rows']);assert sha(BATCH2/spec['rows'])==lock['test_rows_sha256']
    pack=read(ROOT/'manifests/first42_v1.json');entries=[e for e in pack['entries'] if e['id']=='Base' or e['root']==str(BATCH2)]
    ids=[e['id'] for e in entries];assert len(ids)==31 and ids[0]=='Base'
    old_ids=['baseline']+['candidate_'+i for i in ids[1:]];token_index={r['token']:i for i,r in enumerate(rows)}
    scores=np.full((len(rows),len(ids),5,7),np.nan,dtype=np.float64)
    trajectories=np.full((len(rows),len(ids),5,8,3),np.nan,dtype=np.float32);seen=np.zeros(len(rows),dtype=bool)
    def extract(task):
        receipt=read(stage/'receipts'/(task['id']+'.json'));path=BATCH2/receipt['result']['path'];assert sha(path)==receipt['result']['sha256'];result=read(path)
        lookup={(r['token'],r['arm'],r['seed_index']):r for r in result['records']};indices=spec['panel'][task['start']:task['end']]
        qs=[];ts=[]
        for index in indices:
            token=rows[index]['token'];assert token_index[token]==index
            q=[];t=[]
            for ident in old_ids:
                qq=[];tt=[]
                for j in range(5):
                    record=lookup[token,ident,j];assert record['seed']==seed(token,j)
                    qq.append([record['score'][f] for f in FIELDS]);tt.append(record['trajectory'])
                q.append(qq);t.append(tt)
            qs.append(q);ts.append(t)
        return indices,np.asarray(qs,dtype=np.float64),np.asarray(ts,dtype=np.float32),dict(path=str(path),sha256=receipt['result']['sha256'])
    sources=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for indices,q,t,source in pool.map(extract,read(stage/'tasks.json')):
            assert not seen[indices].any();seen[indices]=True;scores[indices]=q;trajectories[indices]=t;sources.append(source)
    assert seen.all() and np.isfinite(scores).all() and np.isfinite(trajectories).all()
    folder=ROOT/'provenance/test_shared_reference_v1';array=folder/'REFERENCE.npz';assert not array.exists()
    hashed=save_arrays(array,dict(scores=scores,trajectories=trajectories))
    atomic(folder/'PACK.json',dict(status='ARCHIVED_REFERENCE_FOR_REPLAY_VERIFICATION_ONLY',time=stamp(),cases=len(rows),candidate_ids=ids,seeds=[0,1,2,3,4],fields=FIELDS,
           test_rows_sha256=lock['test_rows_sha256'],first42_pack_sha256=sha(ROOT/'manifests/first42_v1.json'),array=str(array.relative_to(ROOT)),array_sha256=hashed,sources=sources,
           no_candidate_selection=True,no_teacher_targets_created=True))
    print(json.dumps(dict(event='ARCHIVED_SHARED_REFERENCE_READY',cases=len(rows),candidates=len(ids))),flush=True)


def verify(stage_name):
    import numpy as np
    from r3_incremental_audit_v1 import FIELDS
    folder=ROOT/'provenance/test_shared_reference_v1';reference=read(folder/'PACK.json');array=ROOT/reference['array'];assert sha(array)==reference['array_sha256']
    target=ROOT/'analysis'/stage_name/'SUMMARY.json';summary=read(target);assert summary['cohort']=='navtest' and summary['status']=='PASS_COMPLETE_AUDITED_FIRST42'
    assert summary['rows_sha256']==reference['test_rows_sha256'] and summary['pack_sha256']==reference['first42_pack_sha256']
    pack=read(ROOT/'manifests/first42_v1.json');ids=[e['id'] for e in pack['entries']];indices=[ids.index(ident) for ident in reference['candidate_ids']]
    scores=np.load(ROOT/summary['artifacts']['scores.npy']['path'],mmap_mode='r');trajectories=np.load(ROOT/summary['artifacts']['trajectories.npy']['path'],mmap_mode='r')
    with np.load(array,allow_pickle=False) as z:
        assert np.array_equal(np.asarray(scores[:,indices]),z['scores']), 'Shared-score replay mismatch'
        assert np.array_equal(np.asarray(trajectories[:,indices]),z['trajectories']), 'Shared-trajectory replay mismatch'
    output=ROOT/'provenance/FIRST42_FULL_TEST_SHARED_REPLAY_REVIEW.json';assert not output.exists()
    atomic(output,dict(status='PASS_COMPLETE_TEST_BASE_AND30_EXPERTS_ALL_FIVE_EXACT',time=stamp(),cases=summary['cases'],candidates=31,records=summary['cases']*31*5,
           reference_pack_sha256=sha(folder/'PACK.json'),current_summary_sha256=sha(target),all_scores_mapped_by_names=True,no_candidate_or_protocol_changes=True))
    print(json.dumps(dict(status='PASS_FULL_SHARED_TEST_REPLAY',records=summary['cases']*31*5)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--verify-stage');a=p.parse_args()
    if a.prepare:prepare()
    elif a.verify_stage:verify(a.verify_stage)
    else:p.error('one mode required')
