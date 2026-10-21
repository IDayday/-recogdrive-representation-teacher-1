"""One independent 16-card DLC node; both-node smoke gate precedes formal shards."""
from common import *
import argparse
import fcntl
import subprocess
import traceback
from worker import output_dir, population


def latest_records(run, phase, rank):
    path=output_dir(run,phase,rank)
    return [record for file in sorted((path/'chunks').glob('*.json')) for record in read(file)['records']]


def preflight(args, run_root):
    import importlib.metadata
    import torch
    config=read(ROOT/'configs/baseline.json')
    execution=read(ROOT/'configs/execution.json')
    assert execution['run_id']==args.run and execution['identity']==config['identity']
    for path,expected in execution['code_sha256'].items():
        assert sha(ROOT/path)==expected,path
    for item in read(ROOT/'provenance/source_snapshot.json')['files']:
        assert sha(ROOT/item['destination'])==item['sha256'],item['destination']
    assert sha(config['checkpoint'])==config['checkpoint_sha256']
    assert torch.cuda.is_available() and torch.cuda.device_count()==args.devices
    device_info=[dict(index=i,name=torch.cuda.get_device_name(i),memory_bytes=torch.cuda.get_device_properties(i).total_memory)
                 for i in range(args.devices)]
    expected=read(ROOT/'provenance/assets_prepared.json')['versions']
    versions={name:importlib.metadata.version(name) for name in expected}
    assert versions==expected,dict(expected=expected,actual=versions)
    mounts={path:subprocess.check_output(['findmnt','-T',path,'-n','-o','SOURCE,TARGET,FSTYPE,OPTIONS'],text=True).strip()
            for path in ['/mnt/workspace','/mnt/data','/mnt/yehr_workspace']}
    assert '/WM_Group/sjc_workspace' in mounts['/mnt/workspace'],mounts
    assert '/Public_Space' in mounts['/mnt/data'] and '/WM_Group/yehr_workspace' in mounts['/mnt/yehr_workspace'],mounts
    assert 'ro,' in mounts['/mnt/data'] or mounts['/mnt/data'].endswith(' ro'),mounts['/mnt/data']
    assert 'ro,' in mounts['/mnt/yehr_workspace'] or mounts['/mnt/yehr_workspace'].endswith(' ro'),mounts['/mnt/yehr_workspace']
    probe=run_root/'workspace_probe.json'
    atomic(probe,dict(run=args.run,node=args.node_id,time=stamp(),identity=config['identity']))
    assert read(probe)['identity']==config['identity']
    atomic(run_root/'PREFLIGHT.json',dict(status='PASS',time=stamp(),python=sys.executable,versions=versions,
            devices=device_info,memory=subprocess.check_output(['free','-b'],text=True),mounts=mounts,
            code_sha256=execution['code_sha256'],identity=config['identity']))


def run_phase(args, phase, run_root):
    phase_root=run_root/phase
    if (phase_root/'COMPLETE.json').exists():
        return
    handles=[];processes=[]
    began=time.monotonic();last_semantic=began
    try:
        for local_rank in range(args.devices):
            rank=args.node_id*args.devices+local_rank
            out=output_dir(args.run,phase,rank)
            out.mkdir(parents=True,exist_ok=True)
            log=(out/'worker.log').open('a');handles.append(log)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local_rank),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
            for key in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:
                env.pop(key,None)
            command=[sys.executable,'-B',str(ROOT/'code/worker.py'),'--run',args.run,'--phase',phase,
                     '--rank',str(rank),'--world-size',str(args.devices*args.nodes),
                     '--chunk-size','32','--scoring-workers','2']
            processes.append(subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT))
        while True:
            failures=[(args.node_id*args.devices+i,p.returncode) for i,p in enumerate(processes) if p.poll() not in (None,0)]
            if failures:
                details=[]
                for rank,code in failures:
                    path=output_dir(args.run,phase,rank)/'FAILED.json'
                    details.append(read(path) if path.exists() else dict(rank=rank,exit_code=code))
                atomic(phase_root/'FAILED_RANKS.json',dict(status='FAILED',time=stamp(),failures=details))
                raise RuntimeError(f'{phase}: failed ranks {failures}; original exceptions preserved in FAILED_RANKS.json and worker.log')
            statuses=[]
            for local_rank in range(args.devices):
                path=output_dir(args.run,phase,args.node_id*args.devices+local_rank)/'status.json'
                if path.exists():
                    try:statuses.append(read(path))
                    except OSError:pass  # bounded retries already exhausted; keep polling instead of declaring failure
            status=dict(status=phase.upper(),time=stamp(),node_id=args.node_id,phase_seconds=time.monotonic()-began,
                        completed=sum(r.get('completed',0) for r in statuses),
                        requested=sum(r.get('requested',0) for r in statuses),worker_statuses=statuses)
            atomic(run_root/'STATUS.json',status)
            print(json.dumps({k:v for k,v in status.items() if k!='worker_statuses'}),flush=True)
            if phase=='formal' and time.monotonic()-last_semantic>=300:
                observations=[]
                for item in statuses:
                    if item.get('last_chunk'):
                        records=read(item['last_chunk'])['records']
                        assert all(r['valid'] and r['seed']==seed(r['token']) and len(r['trajectory'])==8 for r in records)
                        observations.extend(records)
                counts={kind:sum(r['quality']==kind for r in observations) for kind in ['failure','intermediate','high_quality']}
                atomic(phase_root/f'stage_{int(time.monotonic()-began):06d}.json',dict(status='PASS',time=stamp(),
                       completed=status['completed'],checked_recent_records=len(observations),quality_counts=counts,
                       mean_recent_pdms_100=100*sum(r['score']['score'] for r in observations)/max(len(observations),1)))
                last_semantic=time.monotonic()
            if all(p.poll() is not None for p in processes):break
            time.sleep(60)
        receipts=[read(output_dir(args.run,phase,args.node_id*args.devices+i)/'COMPLETE.json') for i in range(args.devices)]
        rows=population()
        expected=args.devices*4 if phase=='smoke' else sum(len(rows[args.node_id*args.devices+i::args.devices*args.nodes]) for i in range(args.devices))
        assert sum(r['completed'] for r in receipts)==expected
        assert all(r['all_parameters_fp32'] and r['no_gradients'] and r['parameter_versions_unchanged'] for r in receipts)
        atomic(phase_root/'COMPLETE.json',dict(status='COMPLETE',node_id=args.node_id,time=stamp(),samples=expected,workers=receipts,
                all_worker_exit_codes=[p.returncode for p in processes],seconds=time.monotonic()-began))
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for handle in handles:handle.close()


def both_node_gate(args, run_root):
    import numpy as np
    base=ROOT/'runs'/args.run
    gate=base/'BOTH_NODE_SMOKE_PASS.json'
    began=time.monotonic()
    while not gate.exists():
        for node in range(args.nodes):
            failure=base/f'node{node}/FAILED.json'
            if failure.exists():raise RuntimeError(f'peer node failed: {failure}; inspect original exception')
        ready=[base/f'node{i}/smoke/COMPLETE.json' for i in range(args.nodes)]
        if all(p.exists() for p in ready):
            execution=read(ROOT/'configs/execution.json')
            dsw=latest_records(execution['dsw_smoke_run'],'dsw_smoke',0)
            anchors={r['token']:r for r in dsw[:2]}
            maximum=0.
            for rank in range(args.devices*args.nodes):
                eq=read(output_dir(args.run,'smoke',rank)/'SCORING_EQUIVALENCE.json')
                assert eq['status']=='PASS' and eq['max_score_difference']==0
                records=latest_records(args.run,'smoke',rank)
                for r in records[:2]:
                    ref=anchors[r['token']]
                    assert r['feature_sha256']==ref['feature_sha256'] and r['seed']==ref['seed']
                    delta=float(np.max(np.abs(np.asarray(r['trajectory'])-np.asarray(ref['trajectory']))))
                    maximum=max(maximum,delta)
                    assert delta<=1e-6,(rank,r['token'],delta)
                    assert all(abs(r['score'][k]-ref['score'][k])<=1e-8 for k in r['score'])
            atomic(gate,dict(status='PASS',time=stamp(),ranks=args.devices*args.nodes,
                            samples=args.devices*args.nodes*4,max_trajectory_difference_from_dsw=maximum,
                            independent_scoring_difference=0,seed_rank_independent=True,test_cache_access=False))
            break
        if time.monotonic()-began>3600:raise TimeoutError('Both-node smoke barrier exceeded one hour')
        atomic(run_root/'STATUS.json',dict(status='WAITING_FOR_BOTH_NODE_SMOKE',time=stamp(),seconds=time.monotonic()-began))
        time.sleep(15)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--node-id',type=int,required=True)
    parser.add_argument('--run',required=True)
    parser.add_argument('--devices',type=int,default=16)
    parser.add_argument('--nodes',type=int,default=2)
    args=parser.parse_args()
    assert args.nodes==2 and args.devices==16 and 0<=args.node_id<args.nodes
    setup(f'{args.run}/coordinator{args.node_id}')
    run_root=ROOT/'runs'/args.run/f'node{args.node_id}'
    run_root.mkdir(parents=True,exist_ok=True)
    handle=(run_root/'coordinator.lock').open('a+')
    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        preflight(args,run_root)
        run_phase(args,'smoke',run_root)
        both_node_gate(args,run_root)
        run_phase(args,'formal',run_root)
        atomic(run_root/'NODE_COMPLETE.json',dict(status='COMPLETE',time=stamp(),node_id=args.node_id))
        atomic(run_root/'STATUS.json',dict(status='COMPLETE',time=stamp(),node_id=args.node_id))
        if all((ROOT/'runs'/args.run/f'node{i}/NODE_COMPLETE.json').exists() for i in range(args.nodes)):
            lock=(ROOT/'runs'/args.run/'finalize.lock').open('a+')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            subprocess.run([sys.executable,'-B',str(ROOT/'code/finalize.py'),'--run',args.run],check=True,cwd=ROOT)
    except BaseException as error:
        atomic(run_root/'FAILED.json',dict(status='FAILED',time=stamp(),node_id=args.node_id,error=repr(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':
    main()
