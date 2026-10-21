"""Task-private DLC paired-observation coordinator and foreground terminal monitor."""
from common import *
import argparse
import importlib.metadata
import subprocess
import traceback


def preflight(args):
    import torch
    execution=read(args.execution);base=ROOT/'runs'/args.run
    assert execution['run']==args.run and execution['devices']==args.devices
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    for item in read(ROOT/'provenance/source_snapshot.json')['files']:
        assert sha(ROOT/item['destination'])==item['sha256'],item['destination']
    cfg=read(ROOT/'configs/baseline.json');assert sha(cfg['checkpoint'])==cfg['checkpoint_sha256']
    protocol=read(ROOT/execution['protocol']);assert protocol['identity']==execution['identity']
    assert sha(ROOT/protocol['references'])==protocol['references_sha256']
    assert torch.cuda.is_available() and torch.cuda.device_count()==args.devices
    versions={k:importlib.metadata.version(k) for k in read(ROOT/'provenance/assets_prepared.json')['versions']}
    assert versions==read(ROOT/'provenance/assets_prepared.json')['versions']
    mounts={p:subprocess.check_output(['findmnt','-T',p,'-n','-o','SOURCE,TARGET,FSTYPE,OPTIONS'],text=True).strip()
            for p in ['/mnt/workspace','/mnt/data','/mnt/yehr_workspace']}
    assert '/WM_Group/sjc_workspace' in mounts['/mnt/workspace']
    for p,source in [('/mnt/data','/Public_Space'),('/mnt/yehr_workspace','/WM_Group/yehr_workspace')]:
        assert source in mounts[p] and ('ro,' in mounts[p] or mounts[p].endswith(' ro')),mounts[p]
    atomic(base/'PREFLIGHT.json',dict(status='PASS',time=stamp(),devices=[dict(index=i,
        name=torch.cuda.get_device_name(i),memory_bytes=torch.cuda.get_device_properties(i).total_memory) for i in range(args.devices)],
        versions=versions,mounts=mounts,cpu=os.cpu_count(),memory=subprocess.check_output(['free','-b'],text=True),
        identity=protocol['identity'],code_sha256=execution['code_sha256']))
    return execution,protocol


def launch_phase(args,execution,protocol,phase):
    base=ROOT/'runs'/args.run;children=[];logs=[];began=time.monotonic();last_check=began
    try:
        for rank in range(args.devices):
            folder=base/phase/f'rank{rank:03d}';folder.mkdir(parents=True,exist_ok=True)
            stream=(folder/'worker.log').open('a');logs.append(stream)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(rank),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
            command=[sys.executable,'-B',str(ROOT/'code/paired_observation.py'),'collect','--run',args.run,
                '--phase',phase,'--rank',str(rank),'--world-size',str(args.devices),'--scoring-workers','3',
                '--references',str(ROOT/protocol['references']),'--protocol',str(ROOT/execution['protocol'])]
            children.append(subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT))
        while True:
            failed=[dict(rank=i,exit_code=p.returncode) for i,p in enumerate(children) if p.poll() not in (None,0)]
            if failed:
                atomic(base/f'FAILED_{phase}_RANKS.json',dict(failures=failed,time=stamp()))
                raise RuntimeError(f'Failed ranks preserved: {failed}; see original per-rank exception and worker.log')
            statuses=[]
            for rank in range(args.devices):
                path=base/phase/f'rank{rank:03d}'/'STATUS.json'
                if path.exists():
                    try:statuses.append(read(path))
                    except OSError:pass
            status=dict(status=phase.upper(),time=stamp(),completed=sum(s.get('completed',0) for s in statuses),
                total=len(protocol['pilot_tokens']) if phase=='pilot' else 2288,seconds=time.monotonic()-began)
            atomic(base/'STATUS.json',status);print(json.dumps(status),flush=True)
            if phase=='formal' and time.monotonic()-last_check>=300:
                sample=[]
                for rank in range(args.devices):
                    files=sorted((base/phase/f'rank{rank:03d}'/'scenes').glob('*.json'))
                    if files:sample.extend(read(files[-1])['records'])
                assert all(r['quality']==quality(r['score']['score']) and r['executed_timesteps'][-1]==0 and len(r['trajectory'])==8 for r in sample)
                assert all(r['identity']==protocol['identity'] for r in sample)
                from paired_acceptance import summarize
                atomic(base/f'stage_{int(time.monotonic()-began):06d}.json',dict(status='PASS',time=stamp(),
                    **summarize(sample,protocol),completed_scenes=status['completed']))
                last_check=time.monotonic()
            if all(p.poll() is not None for p in children):break
            time.sleep(60)
        receipts=[read(base/phase/f'rank{i:03d}'/'COMPLETE.json') for i in range(args.devices)]
        assert all(r['parameters_unchanged'] and r['no_gradients'] for r in receipts)
        atomic(base/f'{phase}_WORKERS_COMPLETE.json',dict(status='COMPLETE',time=stamp(),workers=receipts,
                exit_codes=[p.returncode for p in children]))
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for s in logs:s.close()
    command=[sys.executable,'-B',str(ROOT/'code/paired_acceptance.py'),'--run',args.run,'--phase',phase,
             '--protocol',str(ROOT/execution['protocol'])]
    if phase=='pilot':command.extend(['--anchor-run',execution['dsw_pilot']])
    subprocess.run(command,check=True,cwd=ROOT)


def monitor(args):
    from cloud_api import request
    execution=read(args.execution);base=ROOT/'runs'/args.run
    job_id=read(ROOT/execution['submission'])['JobId']
    while True:
        try:
            job=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job_id)
            cloud={k:job[k] for k in ['JobId','Status','ReasonCode','ReasonMessage','GmtStartTime','GmtEndTime'] if k in job}
        except Exception as e:cloud=dict(JobId=job_id,Status='QUERY_ERROR',error=str(e))
        status=read(base/'STATUS.json') if (base/'STATUS.json').exists() else dict(status='SCHEDULING')
        snapshot=dict(time=stamp(),cloud=cloud,work=status)
        atomic(base/'MONITOR.json',snapshot);print(json.dumps(snapshot),flush=True)
        if (base/'FAILED.json').exists() or cloud['Status'] in {'Failed','Stopped','Deleted'}:raise RuntimeError('DLC observation failed; inspect preserved original exception')
        if cloud['Status']=='Succeeded':
            assert (base/'COMPLETE.json').exists()
            atomic(base/'MONITOR_COMPLETE.json',dict(status='PASS',time=stamp(),cloud=cloud))
            return
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','monitor']);p.add_argument('--run',required=True)
    p.add_argument('--execution',required=True,type=Path);p.add_argument('--devices',type=int,default=8);args=p.parse_args()
    setup(f'{args.run}/coordinator');compatibility()
    if args.command=='monitor':monitor(args)
    else:
        try:
            execution,protocol=preflight(args)
            launch_phase(args,execution,protocol,'pilot')
            launch_phase(args,execution,protocol,'formal')
            atomic(ROOT/'runs'/args.run/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),identity=protocol['identity']))
            atomic(ROOT/'runs'/args.run/'STATUS.json',dict(status='COMPLETE',time=stamp(),scenes=2288))
        except BaseException as e:
            atomic(ROOT/'runs'/args.run/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()))
            raise
