"""Explicit stage transitions; only exploration screens select interventions and fit gates."""
from common import *
import argparse
import subprocess
from repair_queue import stage
from repair_analysis import summarize,select

def initial_validation(base):
    for name in ['screen','natural_learn_screen']:
        output=ROOT/'repair_v1/analysis'/name/'SUMMARY.json'
        if not output.exists():summarize(base,name)
    selection=ROOT/'repair_v1/SELECTION.json'
    arms=read(selection)['validation_arms'] if selection.exists() else select(base)
    arm_path=ROOT/'repair_v1/selected_validation_arms.json'
    if arm_path.exists():assert read(arm_path)==arms
    else:atomic(arm_path,arms)
    proof=ROOT/'repair_v1/SELECTED_GATE_SMOKE.json'
    if not proof.exists():
        subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_gate_smoke.py'),'--arms',str(arm_path.relative_to(ROOT)),
            '--output',str(proof.relative_to(ROOT))],check=True,cwd=ROOT)
    assert read(proof)['arms_sha256']==sha(arm_path)
    count=stage(base,'validation_repair',read(ROOT/'repair_v1/validation.json'),arms,[0,1,2],chunk=8)
    atomic(ROOT/'repair_v1/VALIDATION_ENQUEUED.json',dict(time=stamp(),arms=len(arms),scenes=17475,seeds=[0,1,2],tasks=count))
    print(json.dumps(dict(status='VALIDATION_ENQUEUED',arms=len(arms),tasks=count)),flush=True)

def extra_validation(base):
    combined=[]
    for name in ['sensitivity_screen','budget_control','early_quality_screen']:
        path=ROOT/'repair_v1/analysis'/name/'SUMMARY.json'
        result=read(path) if path.exists() else summarize(base,name)
        combined.extend(dict(r,stage=name) for r in result['summaries'])
    categories=[('dimension',k) for k in [4,16,32]]+[('stage','budget_control'),('stage','early_quality_screen')]
    chosen=[]
    for field,value in categories:
        group=[r for r in combined if (r['arm']['k']==value if field=='dimension' else r['stage']==value) and not r['arm'].get('control',False)]
        bounded=[r for r in group if r['high_damage_to_failure_rate']<=.005]
        best=max(bounded or group,key=lambda r:r['population_weighted_screen_delta']);chosen.append(best)
    arms=[r['arm'] for r in chosen];atomic(ROOT/'repair_v1/extra_validation_selection.json',dict(time=stamp(),chosen=chosen,fit_and_selection='exploration only'))
    path=ROOT/'repair_v1/extra_validation_arms.json';atomic(path,arms)
    proof=ROOT/'repair_v1/EXTRA_VALIDATION_SMOKE.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_gate_smoke.py'),'--arms',str(path.relative_to(ROOT)),
        '--output',str(proof.relative_to(ROOT))],check=True,cwd=ROOT)
    count=stage(base,'validation_extra',read(ROOT/'repair_v1/validation.json'),arms,[0,1,2],chunk=16)
    atomic(ROOT/'repair_v1/EXTRA_VALIDATION_ENQUEUED.json',dict(time=stamp(),arms=len(arms),tasks=count))
    print(json.dumps(dict(status='EXTRA_VALIDATION_ENQUEUED',arms=len(arms),tasks=count)),flush=True)

def preservation_validation(base):
    # The first selector preserves mechanisms; additionally keep the low-damage Pareto end.
    combined=[]
    for name in ['screen','natural_learn_screen']:
        result=read(ROOT/'repair_v1/analysis'/name/'SUMMARY.json');combined.extend(dict(r,stage=name) for r in result['summaries'])
    choices=[]
    for method,source,natural_input in [('local','n',True),('linear','n',True),('mlp','n',True),('contract','p',False),('mean','p',False)]:
        group=[r for r in combined if r['arm']['method']==method and r['arm']['source']==source and bool(r['arm'].get('natural_input_training',False))==natural_input]
        bounded=[r for r in group if r['high_damage_to_failure_rate']<=.001]
        choices.append(max(bounded or group,key=lambda r:r['population_weighted_screen_delta']))
    already={a['id'] for a in read(ROOT/'repair_v1/selected_validation_arms.json')}
    arms=[r['arm'] for r in choices if r['arm']['id'] not in already]
    path=ROOT/'repair_v1/preservation_validation_arms.json';atomic(path,arms)
    atomic(ROOT/'repair_v1/PRESERVATION_SELECTION.json',dict(time=stamp(),selection='exploration-only low-damage Pareto controls, including natural-success replay models',choices=choices))
    proof=ROOT/'repair_v1/PRESERVATION_VALIDATION_SMOKE.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_gate_smoke.py'),'--arms',str(path.relative_to(ROOT)),
        '--output',str(proof.relative_to(ROOT))],check=True,cwd=ROOT)
    tasks=stage(base,'validation_preservation',read(ROOT/'repair_v1/validation.json'),arms,[0,1,2],chunk=16)
    atomic(ROOT/'repair_v1/PRESERVATION_ENQUEUED.json',dict(time=stamp(),arms=len(arms),tasks=tasks))
    print(json.dumps(dict(status='PRESERVATION_ENQUEUED',arms=len(arms),tasks=tasks)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['initial_validation','extra_validation','preservation_validation']);args=p.parse_args();setup('repair/followup');compatibility()
    base=ROOT/'runs'/read(ROOT/'repair_v1/ACTIVE_RUN.json')['run']
    if args.command=='initial_validation':initial_validation(base)
    elif args.command=='extra_validation':extra_validation(base)
    else:preservation_validation(base)
