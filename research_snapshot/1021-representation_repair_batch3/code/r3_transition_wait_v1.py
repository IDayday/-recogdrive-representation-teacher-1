"""Mechanical wait for CPU aggregation, prepared engineering, or node changes."""
from r3_common import *
import argparse


def main(a):
    import psutil
    stage=ROOT/'runs'/a.stage;multi=ROOT/'runs/formed_multi_engineering_v1'
    while True:
        failures=list((multi/'failures').glob('*.json')) if multi.exists() else []
        if failures:
            print(json.dumps(dict(event='FORMED_ENGINEERING_FAILED_REQUIRES_REVIEW',path=str(failures[0]),detail=read(failures[0]),time=stamp())),flush=True);return
        if (stage/'AGENT_ACCEPTANCE.json').exists():
            print(json.dumps(dict(event='TRAIN_AGGREGATION_READY_REQUIRES_REVIEW',path=str(stage/'AGENT_ACCEPTANCE.json'),time=stamp())),flush=True);return
        if multi.exists() and not (ROOT/'provenance/FORMED_RUNTIME_MULTI_DEVICE_ADMISSION.json').exists():
            checklist=read(multi/'DEVICE_CHECKLIST.json');expected=[ROOT/'runs/formed_integration_v1/multi_v1'/n['name']/('device%02d'%d)/'PASS.json' for n in checklist['nodes'] for d in n['devices']]
            if all(p.exists() for p in expected):
                print(json.dumps(dict(event='FORMED_MULTI_DEVICE_READY_REQUIRES_REVIEW',devices=len(expected),time=stamp())),flush=True);return
        alive=[]
        for p in psutil.process_iter(['pid','cmdline']):
            command=p.info['cmdline'] or []
            if any(v.endswith('/r3_finish42_v1.py') for v in command) and a.stage in command:alive.append(p.pid)
        if not alive:
            print(json.dumps(dict(event='CPU_AGGREGATOR_ENDED_WITHOUT_ACCEPTANCE_REVIEW_TERMINAL',stage=a.stage,time=stamp())),flush=True);return
        registry=read(ROOT/'resources/REGISTRY.json');cloud=read(BATCH2/'resources/CLOUD_LATEST.json')
        new=[n for n in cloud['nodes'] if n['job'] in registry.get('pending_jobs',[]) and n['status']=='Running']
        if new:
            print(json.dumps(dict(event='NEW_RUNNING_NODE_REQUIRES_PREFLIGHT',nodes=new,time=stamp())),flush=True);return
        time.sleep(a.interval)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--interval',type=int,default=60);main(p.parse_args())
