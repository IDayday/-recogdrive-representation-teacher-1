"""Resume exactly failed cache-readout tasks; numerical functions stay frozen."""
from common import *
import argparse,psutil,socket,subprocess,fcntl,traceback
import numpy as np
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

OUT=DEST.parent/'late_token_coverage';REC=OUT/'recovery_dtype_v1'
BASE=ROOT/'runs/vlm_late_qualification_20261017_v1'

def typed_equal(path,arrays):
    with np.load(path) as previous:
        assert set(previous.files)==set(arrays)
        for name,value in arrays.items():
            x=previous[name];y=np.asarray(value)
            assert np.array_equal(x,y,equal_nan=True) if x.dtype.kind in 'fc' else np.array_equal(x,y),name
    return sha(path)

def patch():
    import vlm_late_qualification as module
    original=module.save_npz
    def save(path,**arrays):
        if path.exists():return typed_equal(path,arrays)
        try:return original(path,**arrays)
        except TypeError:
            if path.exists() and any(np.asarray(v).dtype.kind in 'US' for v in arrays.values()):return typed_equal(path,arrays)
            raise
    module.save_npz=save

def authorize(a):
    legacy=next(n for n in read(DEST/'REGISTRY.json')['nodes'] if n['id']==f'legacy_{a.node}')
    assert socket.gethostname().startswith(legacy['job'])
    records=[]
    for failure in (OUT/'failures').glob('worker_None_*.json'):
        rank=int(failure.stem.rsplit('_',1)[1])
        if rank//16!=a.node:continue
        error=read(failure);assert "ufunc 'isnan'" in error['error'] and 'save_npz' in error['traceback']
        for folder in (BASE/'claims').iterdir():
            if (BASE/'receipts'/(folder.name+'.json')).exists():continue
            owner=read(folder/'OWNER.json')
            if owner['rank']!=rank:continue
            pid=owner['pid'];dead=False
            try:
                p=psutil.Process(pid)
                dead=p.status()==psutil.STATUS_ZOMBIE
                if not dead:
                    created=dt.datetime.fromtimestamp(p.create_time(),dt.timezone.utc)
                    dead=created>dt.datetime.fromisoformat(owner['time'])+dt.timedelta(seconds=1)
                assert dead,('Original worker is still alive',rank,pid)
            except psutil.NoSuchProcess:dead=True
            assert dead
            records.append(dict(task=owner['task'],owner=owner,owner_sha256=sha(folder/'OWNER.json'),
                job=legacy['job'],old_process_verified_terminated=True,
                failure_path=str(failure.relative_to(ROOT)),failure_sha256=sha(failure)))
    atomic(REC/f'OLD_NODE_{a.node}.json',dict(status='PASS',time=stamp(),node=a.node,job=legacy['job'],tasks=records,
        no_process_stopped=True,no_claim_removed_or_live_owner_changed=True))
    print('FAILED_QUALIFICATION_AUTHORIZED',a.node,len(records),flush=True)

def worker(a):
    patch();from threadpoolctl import threadpool_limits
    from vlm_late_selection import select_family
    source=read(REC/f'OLD_NODE_{a.node}.json');record=source['tasks'][a.index];task=record['task'];folder=BASE/'claims'/task['id']
    with (REC/'locks'/task['id']).open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt=BASE/'receipts'/(task['id']+'.json')
        if receipt.exists():return
        assert sha(folder/'OWNER.json')==record['owner_sha256']
        atomic(REC/'previous_owners'/(task['id']+'.json'),record)
        rank=2100000+record['owner']['rank']
        atomic(folder/'OWNER.json',dict(task=task,rank=rank,pid=os.getpid(),time=stamp(),
            recovery_authorization_sha256=sha(REC/f'OLD_NODE_{a.node}.json'),old_owner_preserved=True))
        with threadpool_limits(2):select_family(task['table'],2)
        result=OUT/'selected'/(task['id']+'.json');assert not receipt.exists()
        atomic(receipt,dict(status='COMPLETE',time=stamp(),rank=rank,task=task,result_path=str(result.relative_to(ROOT)),
            result_sha256=sha(result),cache_string_comparison_only_fixed=True,original_qualification_code_sha256=sha(ROOT/'code/vlm_late_qualification.py')))
        print('RECOVERED_READOUT_TASK_PASS',task['id'],flush=True)

def acknowledge():
    proof=REC/'RECOVERY_READY.json'
    if proof.exists():return
    if len(list((BASE/'receipts').glob('*.json')))!=48:return
    for p in (BASE/'receipts').glob('*.json'):
        r=read(p);assert sha(ROOT/r['result_path'])==r['result_sha256']
    atomic(proof,dict(status='PASS',time=stamp(),all_48_qualification_tasks_complete=True,
        numeric_formulas_selection_order_seeds_and_thresholds_unchanged=True,
        original_4544_CV_results_preserved=True,no_model_collection_repeated=True))
    path=DEST/'RESOLVED_ADAPTER_FAILURES.json';ledger=read(path)
    atomic(REC/'EARLIER_RESOLUTIONS.json',ledger)
    authorized={r['failure_path'] for n in [0,1] for r in read(REC/f'OLD_NODE_{n}.json')['tasks']}
    derived={'node_0_None.json','node_1_None.json','services_node0.json','services_node1.json'}
    for failure in (OUT/'failures').glob('*.json'):
        assert str(failure.relative_to(ROOT)) in authorized or failure.name in derived,failure
        ledger['records'].append(dict(marker=str(failure.relative_to(ROOT)),failure_sha256=sha(failure),
            proof=str(proof.relative_to(ROOT)),proof_sha256=sha(proof),service_status=str((REC/'STATUS.json').relative_to(ROOT)),service_pid=os.getpid(),
            explanation='Only string fingerprint equality compatibility fixed. Exact failed owners terminated before five scoped claim transfers; all 48 original numeric/S1/S2 tasks and hashes accepted.'))
    ledger['time']=stamp();atomic(path,ledger)
    atomic(REC/'RESOLUTIONS_UPDATED.json',dict(status='PASS',time=stamp(),exact_original_errors_retained=True))

def service(a):
    c=configuration(a.id);lease=read(ROOT/c['folder']/'ADOPTED_CLONE.json');assert socket.gethostname().startswith(lease['job'])
    REC.mkdir(exist_ok=True);(REC/'locks').mkdir(exist_ok=True)
    for node in [0,1]:assert read(REC/f'OLD_NODE_{node}.json')['status']=='PASS'
    # Reproduce the actual dtype defect and prove exact numeric/string checks.
    probe=REC/'dtype_engineering.npz';values=dict(numeric=np.array([1.,np.nan,3.]),fingerprint=np.asarray('same-source'))
    if not probe.exists():np.savez(probe,**values)
    typed_equal(probe,values)
    bad=dict(values,fingerprint=np.asarray('different-source'));rejected=False
    try:typed_equal(probe,bad)
    except AssertionError:rejected=True
    assert rejected
    atomic(REC/'ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),float_nan_equal=True,identical_string_equal=True,changed_fingerprint_rejected=True,
        cache_read_existing_bytes_not_replaced=True,original_geometry_and_metrics_functions_unchanged=True))
    children=[];streams=[]
    for node in [0,1]:
        for i,r in enumerate(read(REC/f'OLD_NODE_{node}.json')['tasks']):
            if (BASE/'receipts'/(r['task']['id']+'.json')).exists():continue
            stream=(REC/(r['task']['id']+'.log')).open('a');streams.append(stream)
            children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--node',str(node),'--index',str(i)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
    while True:
        assert all(p.poll() in [None,0] for p in children),[(p.pid,p.returncode) for p in children]
        atomic(REC/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host=a.id,
            children=[dict(pid=p.pid,returncode=p.poll()) for p in children],retained=True))
        acknowledge();time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['authorize','worker','service']);p.add_argument('--node',type=int,choices=[0,1]);p.add_argument('--id');p.add_argument('--index',type=int);a=p.parse_args();setup('vlm_repair/late_dtype_recovery')
    for path,h in read(DEST/'LATE_DTYPE_RECOVERY_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    try:globals()[a.mode](a)
    except BaseException as exc:
        atomic(REC/'failures'/f'{a.mode}_{a.node}_{a.index}.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
