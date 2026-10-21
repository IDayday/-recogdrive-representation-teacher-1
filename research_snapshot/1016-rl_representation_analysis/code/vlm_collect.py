"""Broad all-layer VLM collection inside the retained containers; resumable atomic chunks."""
from common import *
import argparse
import subprocess
import traceback
import uuid
from repair_queue_v2 import atomic_unique as atomic,claim,append
from vlm_core import VOUT,VISION_GROUPS,LANGUAGE_GROUPS
import numpy as np

RUN='vlm_all_layers_20261016_v1'

def prepare():
    panel=sorted(read(ROOT/'manifests/natural_s0.json'),key=lambda r:(r['raw_path'],int(r['frame_index'])))
    base=ROOT/'runs'/RUN;assert not (base/'tasks.json').exists()
    atomic(base/'panel.json',panel)
    tasks=[dict(id=f'collect_{i:06d}',start=i,end=min(i+16,len(panel)),phase='collection') for i in range(0,len(panel),16)]
    atomic(base/'PROTOCOL.json',dict(status='FROZEN',time=stamp(),scenes=len(panel),tasks=len(tasks),panel_sha256=sha(base/'panel.json'),
        all_vision_blocks=24,all_language_blocks=28,vision_embedding=True,language_input_and_final_norm=True,
        all_visual_language_bridge_modules=4,bridge_input=True,action_interface_input_and_output=True,
        vision_groups=VISION_GROUPS,language_groups=LANGUAGE_GROUPS,natural_noise_independent=True,
        activation_storage_dtype='float32 pooled from original BF16; no additional quantization',missing_group='NaN plus explicit masks; never zero-filled for analysis',
        labels='frozen S0 primary, repeated S0-S2 stability secondary; training only',test_access=False))
    append(base,tasks);print(json.dumps(dict(status='PREPARED',run=RUN,tasks=len(tasks))),flush=True)

def worker(args):
    setup(f'vlm_repair/collection/rank{args.rank:03d}');compatibility()
    import torch
    from vlm_core import smoke,raw_features
    base=ROOT/'runs'/RUN;status=base/'workers'/f'rank{args.rank:03d}.json'
    try:
        runtime=smoke(base/'smoke'/f'rank{args.rank:03d}.json',anchors=2,return_runtime=True)
        while not (base/f'node{args.rank//16}/SMOKE_PASS.json').exists():
            atomic(status,dict(status='WAIT_LOCAL_SMOKE',time=stamp(),rank=args.rank));time.sleep(2)
        panel=read(base/'panel.json');assert sha(base/'panel.json')==read(base/'PROTOCOL.json')['panel_sha256']
        count=0;began=time.monotonic()
        while True:
            task=claim(base,args.rank)
            if task=='CLOSED':raise RuntimeError('Collection queue must stay open')
            if task is None:
                atomic(status,dict(status='QUEUE_WAIT',time=stamp(),rank=args.rank,tasks_done=count));time.sleep(5);continue
            atomic(status,dict(status='COMPUTING',time=stamp(),rank=args.rank,task=task['id'],tasks_done=count))
            records=[];blocks={}
            for row in panel[task['start']:task['end']]:
                raw=raw_features(row);hidden,values,layout=runtime.forward(raw)
                for name,value in values.items():blocks.setdefault(name,[]).append(value)
                records.append(dict(token=row['token'],global_index=row['global_index'],session=row['session'],subset=row['subset'],
                    layout=layout,source_S0_quality=row['quality']))
            arrays={k:np.stack(v) for k,v in blocks.items()};arrays['global_indices']=np.array([r['global_index'] for r in records],dtype=np.int64)
            destination=base/'arrays'/(task['id']+'.npz');destination.parent.mkdir(parents=True,exist_ok=True);assert not destination.exists()
            tmp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
            with tmp.open('wb') as f:np.savez(f,**arrays)
            tmp.replace(destination);proof=dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,records=records,
                array_path=str(destination.relative_to(ROOT)),array_sha256=sha(destination),shapes={k:list(v.shape) for k,v in arrays.items()})
            atomic(base/'results'/(task['id']+'.json'),proof);atomic(base/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),rank=args.rank,task=task,result_sha256=sha(base/'results'/(task['id']+'.json'))))
            runtime.verify_weights();count+=1
            atomic(status,dict(status='RUNNING',time=stamp(),rank=args.rank,tasks_done=count,seconds=time.monotonic()-began,last_task=task['id']))
    except BaseException as error:
        atomic(base/'failures'/f'rank{args.rank:03d}.json',dict(status='FAILED',time=stamp(),rank=args.rank,error=repr(error),traceback=traceback.format_exc()));raise

def node(args):
    setup(f'vlm_repair/collection/node{args.node}');base=ROOT/'runs'/RUN;folder=base/f'node{args.node}'
    execution=read(VOUT/'COLLECTION_EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    config=read(ROOT/'configs/repair_final_baseline.json')
    for p,h in config['vlm_sha256'].items():assert sha(Path(config['vlm'])/p)==h,p
    assert read(VOUT/'ENGINEERING_SMOKE_v2.json')['status']=='PASS'
    # Leave the existing coordinator and workers alive; wait until their GPU work is done.
    old=ROOT/'runs/candidate_repair_20261016_v1'
    while True:
        states=[read(old/'workers'/f'rank{r:03d}.json')['status'] for r in range(32)]
        if all(s=='QUEUE_WAIT' for s in states) and (old/'stages/final_test/PROTOCOL.json').exists():
            expected=read(old/'stages/final_test/PROTOCOL.json')['tasks']
            if sum(1 for _ in (old/'receipts').glob('final_test_s*.json'))==expected:break
        atomic(folder/'status.json',dict(status='WAIT_CURRENT_GPU_WORK',time=stamp(),old_worker_states=states));time.sleep(10)
    import torch,psutil
    assert torch.cuda.is_available() and torch.cuda.device_count()==16
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),hostname=os.uname().nodename,cards=16,device=torch.cuda.get_device_name(0),
        memory_bytes=torch.cuda.get_device_properties(0).total_memory,host_available_bytes=psutil.virtual_memory().available,
        old_primary_processes_untouched=True))
    processes=[];streams=[];checked=False;started=time.monotonic();last_check=started
    try:
        for local in range(16):
            rank=args.node*16+local;log=(folder/f'rank{rank:03d}.log').open('a');streams.append(log)
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(local),PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            for key in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(key,None)
            processes.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT))
        while True:
            failed=[dict(rank=args.node*16+i,returncode=p.returncode) for i,p in enumerate(processes) if p.poll() is not None]
            if failed:raise RuntimeError(str(failed))
            if not checked and all((base/'smoke'/f'rank{r:03d}.json').exists() for r in range(args.node*16,(args.node+1)*16)):
                reference=read(VOUT/'ENGINEERING_SMOKE_v2.json')['checks']
                for rank in range(args.node*16,(args.node+1)*16):
                    actual=read(base/'smoke'/f'rank{rank:03d}.json')['checks']
                    assert [dict(r,seconds=0) for r in actual]==[dict(r,seconds=0) for r in reference]
                atomic(folder/'SMOKE_PASS.json',dict(status='PASS',time=stamp(),ranks=16,exact_DSW=True));checked=True
            if checked and time.monotonic()-last_check>60:
                done=sum(1 for _ in (base/'receipts').glob('collect_*.json'));atomic(folder/'status.json',dict(status='RUNNING',time=stamp(),tasks=done,total=read(base/'PROTOCOL.json')['tasks']))
                last_check=time.monotonic()
            time.sleep(5)
    except BaseException as error:
        atomic(folder/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int)
    args=p.parse_args();setup('vlm_repair/collection_setup');globals()[args.mode](args) if args.mode!='prepare' else prepare()
