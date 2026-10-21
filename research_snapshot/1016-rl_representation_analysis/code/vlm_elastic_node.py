"""Configurable-card auxiliary node; frozen inference and full-grid math reused."""
from common import *
import argparse,subprocess,traceback,contextlib
from vlm_elastic_registry import DEST,BASE,configuration
from repair_queue_v2 import atomic_unique as atomic

def preflight(c):
    import torch,psutil,importlib.metadata
    for p,h in read(DEST/'EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    for document in [ROOT/'configs/execution.json',VOUT_PATH/'REPAIR_EXECUTION_v6.json']:
        for p,h in read(document)['code_sha256'].items():assert sha(ROOT/p)==h,p
    for item in read(ROOT/'provenance/source_snapshot.json')['files']:
        assert sha(ROOT/item['destination'])==item['sha256']
    assert torch.cuda.is_available() and torch.cuda.device_count()>max(c['devices'])
    assert len(os.sched_getaffinity(0))>=c['cpu_workers']*c['cpu_threads']
    assert psutil.virtual_memory().available>256*1024**3
    mounts={p:subprocess.check_output(['findmnt','-T',p,'-n','-o','SOURCE,TARGET,FSTYPE,OPTIONS'],text=True).strip() for p in ['/mnt/workspace','/mnt/data','/mnt/yehr_workspace']}
    assert '/WM_Group/sjc_workspace' in mounts['/mnt/workspace']
    for p,source in [('/mnt/data','/Public_Space'),('/mnt/yehr_workspace','/WM_Group/yehr_workspace')]:
        assert source in mounts[p] and ('ro,' in mounts[p] or mounts[p].endswith(' ro'))
    expected=read(ROOT/'provenance/assets_prepared.json')['versions']
    versions={k:importlib.metadata.version(k) for k in expected};assert versions==expected
    cfg=read(ROOT/'configs/baseline.json');assert sha(cfg['checkpoint'])==cfg['checkpoint_sha256']
    result=dict(status='PASS',time=stamp(),id=c['id'],cards=c['cards'],gpu_ranks=c['gpu_ranks'],
        devices=[dict(index=i,name=torch.cuda.get_device_name(i),memory=torch.cuda.get_device_properties(i).total_memory) for i in c['devices']],
        cpu=os.cpu_count(),cpu_affinity=len(os.sched_getaffinity(0)),available_memory=psutil.virtual_memory().available,
        mounts=mounts,versions=versions,checkpoint_sha256=cfg['checkpoint_sha256'])
    atomic(ROOT/c['folder']/'PREFLIGHT.json',result)

def cpu(a,c):
    import vlm_scan_queue as module
    original=module.claim
    def claim(tasks,rank,workers):
        if (ROOT/c['folder']/'CPU_DRAIN.json').exists() or (DEST/'FULL_SCAN_COMPLETE.json').exists():return None
        return original(tasks,rank,workers)
    module.claim=claim
    # Unique CPU namespace and its own actual numeric-smoke barrier. No
    # existing reservations/claims, worker identities or outputs are touched.
    a.workers=1024;a.threads=c['cpu_threads'];module.worker(a)

def gpu(a,c):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    import vlm_repair_queue_v6 as module
    from repair_queue_v2 import claim,init_score_unique
    folder=ROOT/c['folder'];state=folder/'gpu_workers'/f'rank{a.rank:03d}.json'
    try:
        setup(f"vlm_repair/elastic/{c['id']}/gpu{a.rank}");compatibility()
        e=module.Engine();fits=module.Fits();versions={k:p._version for k,p in e.agent.named_parameters()}
        module.smoke(e,a.rank,folder/'gpu_validation')
        done=0
        with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
            while True:
                if not (folder/'GPU_SMOKE_PASS.json').exists() or not (folder/'GPU_ENABLED.json').exists() or (folder/'GPU_DRAIN.json').exists():
                    atomic(state,dict(status='WAITING_ACTIVATION',time=stamp(),rank=a.rank,tasks_done=done));time.sleep(5);continue
                task=claim(BASE,a.rank)
                assert task!='CLOSED','Retention protocol forbids queue closure'
                if task is None:
                    atomic(state,dict(status='QUEUE_WAIT',time=stamp(),rank=a.rank,tasks_done=done));time.sleep(5);continue
                owner=BASE/'claims'/task['id']/'OWNER.json';value=read(owner)
                value.update(elastic_node=c['id'],elastic_config_sha256=sha(folder/'CONFIG.json'));atomic(owner,value)
                atomic(state,dict(status='COMPUTING',time=stamp(),rank=a.rank,task=task['id'],tasks_done=done));began=time.monotonic()
                records,timing=module.run_task(e,fits,task,BASE,pool)
                p=BASE/'results'/(task['id']+'.json');assert not p.exists();started=time.monotonic()
                atomic(p,dict(status='COMPLETE',time=stamp(),rank=a.rank,task=task,records=records,timing=timing))
                write_seconds=time.monotonic()-started
                atomic(BASE/'receipts'/p.name,dict(status='COMPLETE',time=stamp(),rank=a.rank,task=task,
                    records=len(records),seconds=time.monotonic()-began,write_seconds=write_seconds,result_sha256=sha(p),
                    elastic_node=c['id'],elastic_config_sha256=sha(folder/'CONFIG.json')))
                done+=1;atomic(state,dict(status='RUNNING',time=stamp(),rank=a.rank,tasks_done=done,last_result=str(p)))
                assert versions=={k:p._version for k,p in e.agent.named_parameters()}
    except BaseException as error:
        atomic(folder/'failures'/f'gpu_rank{a.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=a.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(a,c):
    import psutil,fcntl
    folder=ROOT/c['folder'];folder.mkdir(parents=True,exist_ok=True)
    with (folder/'node.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB);preflight(c)
        children={};streams=[];engineering_child=None
        def launch(kind,rank,device=None):
            stream=(folder/f'{kind}_rank{rank:03d}.log').open('a');streams.append(stream);env=dict(os.environ)
            for key in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(key,None)
            if device is not None:env['CUDA_VISIBLE_DEVICES']=str(device)
            children[f'{kind}_{rank}']=subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),kind,'--id',c['id'],'--rank',str(rank)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        for rank,device in zip(c['gpu_ranks'],c['devices']):launch('gpu',rank,device)
        for rank in range(c['cpu_rank_base'],c['cpu_rank_base']+c['cpu_workers']):launch('cpu',rank)
        atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),id=c['id'],
            processes={name:dict(pid=p.pid,created=psutil.Process(p.pid).create_time()) for name,p in children.items()}))
        while True:
            bad={name:p.poll() for name,p in children.items() if p.poll() is not None};assert not bad,bad
            cpu_smokes=[VOUT_PATH/f'scan/smoke/rank{rank:03d}.json' for rank in range(c['cpu_rank_base'],c['cpu_rank_base']+c['cpu_workers'])]
            barrier=VOUT_PATH/f"scan/node{c['cpu_node']}/SMOKE_PASS.json"
            if not barrier.exists() and all(p.exists() for p in cpu_smokes):
                assert all(read(p)['status']=='PASS' for p in cpu_smokes)
                atomic(barrier,dict(status='PASS',time=stamp(),workers=c['cpu_workers'],threads_per_worker=c['cpu_threads'],elastic_node=c['id'],config_sha256=sha(folder/'CONFIG.json')))
                atomic(folder/'CPU_SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=[read(p)['rank'] for p in cpu_smokes],reference_tolerance=1e-7))
            if not (folder/'GPU_SMOKE_PASS.json').exists():
                probes=[folder/f'gpu_validation/smoke/rank{rank:03d}.json' for rank in c['gpu_ranks']]
                if all(p.exists() for p in probes):
                    reference=read(ROOT/read(VOUT_PATH/'REPAIR_EXECUTION_v6.json')['dsw_reference'])['records']
                    for p in probes:assert read(p)['records']==reference
                    atomic(folder/'GPU_SMOKE_PASS.json',dict(status='PASS',time=stamp(),cards=len(probes),ranks=c['gpu_ranks'],
                        exact_DSW_reference=True,all_62_zero_sites_exact=True,proofs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in probes]))
            if (folder/'GPU_SMOKE_PASS.json').exists() and not (folder/'ENGINEERING_PASS.json').exists() and engineering_child is None:
                stream=(folder/'engineering.log').open('a');streams.append(stream)
                env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(c['devices'][0]))
                engineering_child=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_engineering.py'),'--id',c['id']],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
            if engineering_child is not None and engineering_child.poll() is not None:
                assert engineering_child.returncode==0 and (folder/'ENGINEERING_PASS.json').exists()
            if not (DEST/'FULL_SCAN_COMPLETE.json').exists():
                tasks=read(VOUT_PATH/'scan/tasks.json')
                if len(list((VOUT_PATH/'scan/receipts').glob('*.json')))==len(tasks):
                    atomic(DEST/'FULL_SCAN_COMPLETE.json',dict(status='PASS',time=stamp(),tasks=len(tasks)))
            atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),id=c['id'],
                cpu_smoke_pass=barrier.exists(),gpu_smoke_pass=(folder/'GPU_SMOKE_PASS.json').exists(),
                gpu_enabled=(folder/'GPU_ENABLED.json').exists(),children={name:p.pid for name,p in children.items()},
                main_process_retained=True,no_automatic_release=True))
            time.sleep(15)

VOUT_PATH=DEST.parent
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['node','cpu','gpu']);p.add_argument('--id',required=True);p.add_argument('--rank',type=int);a=p.parse_args();c=configuration(a.id)
    setup(f'vlm_repair/elastic/{a.id}/{a.mode}/{a.rank}')
    try:globals()[a.mode](a,c)
    except BaseException as error:
        folder=ROOT/c['folder'];atomic(folder/'failures'/f'{a.mode}_{a.rank}.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        if a.mode!='node':raise
        while True:time.sleep(30)
