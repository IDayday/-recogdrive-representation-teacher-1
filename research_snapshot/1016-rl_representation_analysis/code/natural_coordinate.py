"""Two independent 16-card nodes capture route-one natural S0, not paired data."""
from common import *
import argparse
import fcntl
import subprocess
import traceback


def preflight(args,execution):
    import torch
    import importlib.metadata
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    for p,h in read(ROOT/'configs/execution.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    for item in read(ROOT/'provenance/source_snapshot.json')['files']:
        assert sha(ROOT/item['destination'])==item['sha256'],item['destination']
    assert torch.cuda.is_available() and torch.cuda.device_count()==16
    mounts={p:subprocess.check_output(['findmnt','-T',p,'-n','-o','SOURCE,TARGET,FSTYPE,OPTIONS'],text=True).strip() for p in ['/mnt/workspace','/mnt/data','/mnt/yehr_workspace']}
    assert '/WM_Group/sjc_workspace' in mounts['/mnt/workspace']
    for p,source in [('/mnt/data','/Public_Space'),('/mnt/yehr_workspace','/WM_Group/yehr_workspace')]:
        assert source in mounts[p] and ('ro,' in mounts[p] or mounts[p].endswith(' ro'))
    expected=read(ROOT/'provenance/assets_prepared.json')['versions']
    versions={k:importlib.metadata.version(k) for k in expected};assert versions==expected
    cfg=read(ROOT/'configs/baseline.json');assert sha(cfg['checkpoint'])==cfg['checkpoint_sha256']
    atomic(ROOT/'runs'/args.run/f'node{args.node}/PREFLIGHT.json',dict(status='PASS',time=stamp(),versions=versions,mounts=mounts,
        devices=[dict(index=i,name=torch.cuda.get_device_name(i),memory=torch.cuda.get_device_properties(i).total_memory) for i in range(16)],
        cpu=os.cpu_count(),memory=subprocess.check_output(['free','-b'],text=True),identity=execution['identity']))


def phase(args,name):
    base=ROOT/'runs'/args.run;node=base/f'node{args.node}';children=[];streams=[];began=time.monotonic();last=began
    try:
        for local in range(16):
            rank=args.node*16+local;out=base/name/f'rank{rank:03d}';out.mkdir(parents=True,exist_ok=True)
            stream=(out/'worker.log').open('a');streams.append(stream)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
            cmd=[sys.executable,'-B',str(ROOT/'code/natural_representation.py'),'collect','--run',args.run,'--phase',name,'--rank',str(rank),'--world-size','32']
            children.append(subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
        while True:
            failed=[dict(rank=args.node*16+i,exit_code=p.returncode) for i,p in enumerate(children) if p.poll() not in (None,0)]
            if failed:
                atomic(node/f'{name}_FAILED_RANKS.json',dict(status='FAILED',time=stamp(),failures=failed))
                raise RuntimeError(f'{name} failed ranks: {failed}; original exceptions preserved')
            states=[]
            for rank in range(args.node*16,(args.node+1)*16):
                p=base/name/f'rank{rank:03d}'/'STATUS.json'
                if p.exists():
                    try:states.append(read(p))
                    except OSError:pass
            state=dict(status=name.upper(),time=stamp(),node=args.node,completed=sum(r.get('completed',r.get('scenes',0)) for r in states),
                       requested=sum(r.get('total',r.get('scenes',0)) for r in states),seconds=time.monotonic()-began)
            atomic(node/'STATUS.json',state);print(json.dumps(state),flush=True)
            if name=='formal' and time.monotonic()-last>=300:
                sample=[]
                for rank in range(args.node*16,(args.node+1)*16):
                    p=base/name/f'rank{rank:03d}'/'STATUS.json'
                    if not p.exists():continue
                    state=read(p)
                    if state.get('last_chunk'):sample.extend(read(Path(state['last_chunk']).with_suffix('.json'))['records'])
                assert all(r['source']=='natural_model_S0' and not r['gt_initialization'] and r['exact_baseline_trajectory_replay'] for r in sample)
                assert all(r['seed']==seed(r['token']) and r['quality']==quality(r['score']['score']) for r in sample)
                from collections import Counter
                atomic(node/f'stage_{int(time.monotonic()-began):06d}.json',dict(status='PASS',time=stamp(),checked=len(sample),
                    counts=dict(Counter(r['quality'] for r in sample)),natural_source=True,exact_baseline_replay=True))
                last=time.monotonic()
            if all(p.poll() is not None for p in children):break
            time.sleep(60)
        receipts=[read(base/name/f'rank{rank:03d}'/'COMPLETE.json') for rank in range(args.node*16,(args.node+1)*16)]
        assert all(r['natural_source'] and not r['gt_initialization'] and r['all_trajectories_exact_baseline_replay'] and r['parameters_unchanged'] for r in receipts)
        atomic(node/f'{name}_COMPLETE.json',dict(status='COMPLETE',time=stamp(),workers=receipts,exit_codes=[p.returncode for p in children]))
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for s in streams:s.close()


def gate(args,execution):
    import numpy as np
    base=ROOT/'runs'/args.run;began=time.monotonic()
    while not (base/'BOTH_NODE_SMOKE_PASS.json').exists():
        if any((base/f'node{i}/FAILED.json').exists() for i in range(2)):raise RuntimeError('Peer failed; inspect original node exception')
        if all((base/f'node{i}/smoke_COMPLETE.json').exists() for i in range(2)):
            lock=(base/'gate.lock').open('a+')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:time.sleep(5);continue
            protocol=read(ROOT/'configs/natural_route1_v1.json');anchors=set(protocol['anchors'])
            dsw=ROOT/'runs'/execution['dsw_smoke']/'smoke/rank000/chunks/000000.json'
            ref=read(dsw);index={r['token']:i for i,r in enumerate(ref['records'])}
            with np.load(ref['array_path'],allow_pickle=False) as z:reference={k:z[k] for k in z.files}
            tested=0
            for rank in range(32):
                doc=read(base/'smoke'/f'rank{rank:03d}'/'chunks/000000.json')
                with np.load(doc['array_path'],allow_pickle=False) as z:
                    for i,r in enumerate(doc['records']):
                        if r['token'] not in anchors:continue
                        assert all(np.array_equal(z[k][i],reference[k][index[r['token']]]) for k in z.files)
                        tested+=1
            assert tested==96
            atomic(base/'BOTH_NODE_SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=32,anchors_compared=96,
                all_captured_tensors_noise_and_trajectories_exact=True,natural_source=True,gt_initialization=False))
            break
        if time.monotonic()-began>3600:raise TimeoutError('Both-node smoke wait exceeded 1h')
        atomic(base/f'node{args.node}/STATUS.json',dict(status='WAITING_BOTH_NODE_SMOKE',time=stamp()))
        time.sleep(15)


def run(args):
    execution=read(args.execution);assert execution['run']==args.run
    base=ROOT/'runs'/args.run;node=base/f'node{args.node}';node.mkdir(parents=True,exist_ok=True)
    lock=(node/'coordinator.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        preflight(args,execution);phase(args,'smoke');gate(args,execution);phase(args,'formal')
        atomic(node/'STATUS.json',dict(status='REDUCING_MOMENTS',time=stamp(),node=args.node))
        subprocess.run([sys.executable,'-B',str(ROOT/'code/natural_representation.py'),'reduce','--run',args.run,'--node',str(args.node)],check=True,cwd=ROOT)
        atomic(node/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),node=args.node))
        atomic(node/'STATUS.json',dict(status='COMPLETE',time=stamp(),node=args.node))
        if all((base/f'node{i}/COMPLETE.json').exists() for i in range(2)):
            atomic(base/'COLLECTION_READY.json',dict(status='COMPLETE',time=stamp(),samples=103288,natural_source=True,
                gt_initialization=False,route='route1_natural_S0',analysis_complete=False))
    except BaseException as error:
        atomic(node/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise


def monitor(args):
    from cloud_api import request
    execution=read(args.execution);base=ROOT/'runs'/args.run
    while True:
        jobs=[];states=[]
        for node in range(2):
            job_id=read(ROOT/execution['submissions'][node])['JobId']
            try:
                value=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job_id)
                jobs.append({k:value[k] for k in ['JobId','Status','ReasonCode','ReasonMessage'] if k in value})
            except Exception as e:jobs.append(dict(JobId=job_id,Status='QUERY_ERROR',error=str(e)))
            p=base/f'node{node}/STATUS.json'
            if p.exists():
                try:states.append(read(p))
                except OSError:pass
        value=dict(time=stamp(),jobs=jobs,nodes=states)
        atomic(base/'MONITOR.json',value);print(json.dumps(value),flush=True)
        if any((base/f'node{i}/FAILED.json').exists() for i in range(2)) or any(j['Status'] in ['Failed','Stopped','Deleted'] for j in jobs):raise RuntimeError('Natural route-one collection failed; inspect original exceptions')
        if all(j['Status']=='Succeeded' for j in jobs):
            assert (base/'COLLECTION_READY.json').exists()
            atomic(base/'MONITOR_COMPLETE.json',dict(status='PASS',time=stamp(),jobs=jobs));return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','monitor']);p.add_argument('--run',required=True)
    p.add_argument('--execution',required=True,type=Path);p.add_argument('--node',type=int);args=p.parse_args()
    setup(f'natural/{args.run}/coordinator{args.node}');compatibility()
    if args.command=='run':run(args)
    else:monitor(args)
