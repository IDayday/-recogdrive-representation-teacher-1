"""Stage-by-stage 8xA800 reproduction; no cloud services or credential required."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from continuation.layout import BATCHES,REPO,sha,write_json

def run(module,arguments,environment=None):
    command=[sys.executable,'-B','-m',module]+[str(v)for v in arguments]
    subprocess.run(command,env=environment,check=True,cwd=REPO)

def parallel(module,common,workers,devices=None):
    children=[]
    try:
        for rank in range(workers):
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            if devices is not None:env['CUDA_VISIBLE_DEVICES']=devices[rank]
            command=[sys.executable,'-B','-u','-m',module]+[str(v)for v in common]+['--rank',str(rank),'--world-size',str(workers)]
            children.append(subprocess.Popen(command,cwd=REPO,env=env,start_new_session=True))
        while True:
            codes=[child.poll()for child in children]
            if any(code is not None and code!=0 for code in codes):raise RuntimeError('One shard failed; inspect its original traceback before resuming')
            if all(code==0 for code in codes):return
            time.sleep(1)
    finally:
        for child in children:
            if child.poll()is None:os.killpg(child.pid,signal.SIGTERM)
        for child in children:
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()

def main(a):
    workspace=Path(a.workspace).resolve();paths=Path(a.paths).resolve();root=workspace/BATCHES[3]
    devices=a.devices.split(',')
    if len(devices)!=8 or len(set(devices))!=8:raise ValueError('This matched recipe uses eight distinct local A800 devices')
    common=['--paths',paths,'--workspace',workspace]
    if a.stage=='prepare':
        run('continuation.prepare',['--workspace',workspace])
        run('continuation.doctor',common+['--models-only'])
    elif a.stage=='pilot':
        run('continuation.cache_metrics',common+['--indices',REPO/'configs/continuation_pilot_indices.json'])
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=devices[0])
        run('continuation.generate_targets',common+['--indices',REPO/'configs/continuation_pilot_indices.json','--reference-mode',a.reference_mode],env)
        scenes=json.loads((root/'manifests/R2_TRAINING_SCENES_V2.json').read_text());records=[]
        for index in [0,3902,6]:records.append(json.loads((root/'runs/full_context_replay_v1/cases'/scenes[index]['token']/'RESULT.json').read_text()))
        error=max(v['source_trajectory_max_abs_error']for v in records)
        if a.max_pilot_trajectory_error is not None and error>a.max_pilot_trajectory_error:
            raise ValueError('Pilot trajectory discrepancy exceeds the explicit limit; inspect reference diagnostics before changing the limit')
        write_json(workspace/'PORTABLE_PILOT_ACCEPTANCE.json',dict(status='PASS_THREE_CASE_FIXED_R2_PILOT',
            max_source_trajectory_error=error,configuration_mode=a.reference_mode,paths_sha256=sha(paths),
            source_H_exact_cases=sum(v['source_H_byte_exact']for v in records),cases=3))
    elif a.stage=='cache':
        parallel('continuation.cache_metrics',common,a.cpu_workers)
    elif a.stage=='teacher':
        pilot=json.loads((workspace/'PORTABLE_PILOT_ACCEPTANCE.json').read_text())
        if pilot['paths_sha256']!=sha(paths):raise ValueError('Pilot paths differ')
        folder=root/'runs/full_context_replay_v1/cases';done=sum(1 for p in folder.iterdir()if p.is_dir())
        required=max(0,103288-done)*4_300_000+10*(1<<30)
        if shutil.disk_usage(workspace).free<required:raise ValueError(f'Insufficient free space for remaining full-context targets: need about {required/(1<<30):.1f} GiB')
        parallel('continuation.generate_targets',common+['--reference-mode',a.reference_mode],len(devices),devices)
        run('continuation.accept_targets',['--workspace',workspace])
        run('continuation.fresh_configs',['--workspace',workspace,'--world-size','8'])
    elif a.stage=='train':
        run('continuation.doctor',common+['--targets','--hardware','--devices','8'])
        acceptance=json.loads((root/'runs/full_context_replay_v1/AGENT_ACCEPTANCE.json').read_text())
        if acceptance.get('status')!='PASS_COMPLETE_PORTABLE_FIXED_R2_TEACHER':raise ValueError('Generated teacher is not fully accepted')
        for group in a.groups.split(','):
            if group not in ['H','T','HT']:raise ValueError('Unknown group')
            config=root/'configs/portable'/('distillation_a800_fresh_'+group+'.json')
            run_dir=root/'runs'/('distillation_a800_fresh_'+group)
            if (run_dir/'TRAINING_COMPLETE.json').exists():continue
            arguments=common+['--config',config,'--devices',a.devices]
            run('continuation.train',arguments+['--mode','preflight'])
            latest=run_dir/'LATEST_CHECKPOINT.json'
            if latest.exists():
                checkpoint=json.loads(latest.read_text())
                if sha(root/checkpoint['path'])!=checkpoint['sha256']:raise ValueError('Latest training checkpoint is corrupt')
                extra=['--resume',root/checkpoint['path']]
            else:extra=['--fresh']
            run('continuation.train',arguments+['--mode','train']+extra)
    elif a.stage=='evaluate':
        for group in a.groups.split(','):
            run_id='distillation_a800_fresh_'+group;config=root/'configs/portable'/(run_id+'.json')
            complete=json.loads((root/'runs'/run_id/'TRAINING_COMPLETE.json').read_text());ref=complete['final_matched_exposure_checkpoint']
            checkpoint=root/ref['path']
            if sha(checkpoint)!=ref['sha256']:raise ValueError('Final checkpoint changed')
            for cohort,subset,noises,label in [('navtrain','all','0,1,2,3,4','navtrain_s0_s4'),
                ('navtrain','validation','5,6,7,8,9','validation_s5_s9')]+([('navtest','all','0,1,2,3,4,5,6,7,8,9','navtest_s0_s9')]if a.allow_navtest else []):
                if cohort=='navtest':parallel('continuation.cache_metrics',common+['--cohort','navtest'],a.cpu_workers)
                out=workspace/'portable_evaluation'/group/label
                arguments=common+['--config',config,'--checkpoint',checkpoint,'--cohort',cohort,'--subset',subset,'--noises',noises,'--out',out]
                if cohort=='navtest':arguments+=['--allow-navtest']
                parallel('continuation.evaluate',arguments,len(devices),devices)
                run('continuation.summarize',['--input',out])
        if {'T','HT'}<=set(a.groups.split(',')):
            labels=['navtrain_s0_s4','validation_s5_s9']+(['navtest_s0_s9']if a.allow_navtest else [])
            for label in labels:
                run('continuation.compare',['--left',workspace/'portable_evaluation/HT'/label,
                    '--right',workspace/'portable_evaluation/T'/label,
                    '--out',workspace/'portable_evaluation/comparisons'/('HT_minus_T_'+label+'.json')])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--stage',choices=['prepare','pilot','cache','teacher','train','evaluate'],required=True)
    p.add_argument('--devices',default='0,1,2,3,4,5,6,7');p.add_argument('--cpu-workers',type=int,default=16)
    p.add_argument('--groups',default='H,T,HT');p.add_argument('--reference-mode',choices=['record','exact'],default='record')
    p.add_argument('--max-pilot-trajectory-error',type=float);p.add_argument('--allow-navtest',action='store_true')
    main(p.parse_args())
