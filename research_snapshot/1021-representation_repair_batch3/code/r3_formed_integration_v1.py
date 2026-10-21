"""Real generic IO/prefetch/score/target integration versus independent goldens."""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import socket
import traceback


def run(engine,task,pool):
    import numpy as np
    from r3_formed_rollout_v1 import run as evaluate
    from r3_incremental_audit_v1 import FIELDS
    node=task['node'];device=int(os.environ.get('CUDA_VISIBLE_DEVICES','0'))
    if node=='dsw':assert socket.gethostname()==read(ROOT/'resources/DSW_PREFLIGHT_V1.json')['hostname']
    else:
        n=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==node)
        assert socket.gethostname().startswith(n['job']+'-') and device in n['devices']
    dest=ROOT/'runs/formed_integration_v1'/task['name']/node/('device%02d'%device)
    assert not (dest/'PASS.json').exists()
    config=read(ROOT/'configs/formed_integration_v1.json');pack=ROOT/config['pack'];rows=BATCH1/'manifests/natural_s0.json'
    prior=ROOT/'analysis/first42_engineering_v2/SUMMARY.json'
    work=dict(id='formed_integration',stage=str(dest.relative_to(ROOT)),indices=[60,1],pack=str(pack),pack_sha256=sha(pack),rows=str(rows),rows_sha256=sha(rows),
              seeds=[0,1,2,3,4],cohort='navtrain',engineering=True,first42_summary=str(prior),first42_summary_sha256=sha(prior))
    result=evaluate(engine,work,pool);checks=[]
    for ref in read(ROOT/result['path'])['cases']:
        d=read(ROOT/ref['path']);gold=read(ROOT/'runs/formed_engineering_v1/dsw_v2'/(d['token']+'.json'))
        lookup={(r['arm'],r['seed_index']):r for r in gold['records']}
        assert sha(ROOT/d['numeric']['path'])==d['numeric']['sha256']
        with np.load(ROOT/d['numeric']['path'],allow_pickle=False) as z:
            scores=np.array(z['scores']);trajectories=np.array(z['trajectories']);edits=np.array(z['relative_edits'])
            assert scores.shape==(len(d['candidate_ids']),5,7)
            for i,ident in enumerate(d['candidate_ids']):
                for j in range(5):
                    old=lookup[ident,j]
                    assert scores[i,j].tolist()==[old['score'][f] for f in FIELDS]
                    assert trajectories[i,j].tolist()==old['trajectory']
                    assert edits[i,j]==old['relative_edit']
        assert sha(ROOT/d['interfaces']['path'])==d['interfaces']['sha256']
        with np.load(ROOT/d['interfaces']['path'],allow_pickle=False) as actual,np.load(ROOT/gold['interface_path'],allow_pickle=False) as expected:
            for key,r in d['teacher_records'].items():
                h=actual[r['interface_array']];assert np.array_equal(h,expected[key])
                assert hashlib.sha256(h.tobytes()).hexdigest()==r['interface_sha256']
                old=lookup[r['arm'],r['seed_index']];assert r['trajectory']==old['trajectory'] and r['score']==old['score']
        checks.append(dict(token=d['token'],records=len(lookup),all_numeric_trajectories_and_scores_equal_independent_golden=True,
                           exported_targets=len(d['teacher_records']),all_exported_interfaces_equal_independent_golden=True,
                           cache_statistics=d['cache_statistics']))
    proof=dict(status='PASS_GENERIC_INTEGRATION_DEVICE',time=stamp(),node=node,device=device,worker_pid=os.getpid(),hostname=socket.gethostname(),checks=checks,
               result=result,code_hashes={name:sha(ROOT/'code'/name) for name in ['r3_formed_rollout_v1.py','r3_formed_scene_v2.py','r3_inference_cache_v2.py','r3_legacy_runtime_v1.py','r3_select_generic_v1.py']},
               formal_expansion_not_started=True)
    atomic(dest/'PASS.json',proof);return proof


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',default='dsw_v1');a=p.parse_args()
    try:
        setup('formed_integration/'+a.name);compatibility()
        from vlm_intervene_v4 import Engine
        from r3_runtime import init_scorer
        engine=Engine()
        with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
            proof=run(engine,dict(name=a.name,node='dsw'),pool)
        print(json.dumps(dict(event='FORMED_GENERIC_INTEGRATION_PASS',checks=proof['checks'])),flush=True)
    except BaseException as error:
        atomic(ROOT/'runs/formed_integration_v1'/a.name/'DSW_FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
